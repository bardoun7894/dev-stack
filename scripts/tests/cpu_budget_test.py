"""Unit tests for scripts/gate/cpu-budget with faked lscpu / loadavg / meminfo / vm_stat inputs.
Run: python3 -m unittest scripts/tests/cpu_budget_test.py"""
import importlib.machinery
import importlib.util
import os
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "gate" / "cpu-budget"
loader = importlib.machinery.SourceFileLoader("cpu_budget", str(SRC))
spec = importlib.util.spec_from_loader("cpu_budget", loader)
cb = importlib.util.module_from_spec(spec)
loader.exec_module(cb)

# 4 cores x 2 threads, one socket (the laptop i7-4770HQ)
LSCPU_SMT = "# header\n" + "".join(f"{c},0\n" for c in [0, 1, 2, 3, 0, 1, 2, 3])
LSCPU_8 = "# header\n" + "".join(f"{c},0\n" for c in range(8))
MEMINFO = "MemTotal: 16000000 kB\nMemAvailable: 2097152 kB\n"   # 2048 MB
VMSTAT = ("Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
          "Pages free: 32768.\nPages active: 100.\nPages inactive: 32768.\n")  # 1024 MB


def inputs(**kw):
    base = dict(cores=4, logical=8, load1=0.0, mem_mb=8192, per_proc_mb=512, conf={}, env={})
    base.update(kw)
    return base


class Parse(unittest.TestCase):
    def test_linux_cores_unique_core_socket_pairs(self):
        self.assertEqual(cb.parse_lscpu(LSCPU_SMT), 4)
        self.assertEqual(cb.parse_lscpu(LSCPU_8), 8)

    def test_linux_two_sockets_same_core_id_count_twice(self):
        self.assertEqual(cb.parse_lscpu("0,0\n1,0\n0,1\n1,1\n"), 4)

    def test_meminfo_available_mb(self):
        self.assertEqual(cb.parse_meminfo(MEMINFO), 2048)

    def test_vm_stat_free_plus_inactive(self):
        self.assertEqual(cb.parse_vm_stat(VMSTAT), 1024)

    def test_conf(self):
        self.assertEqual(cb.parse_conf("# c\nrole=ci\nmax = 3\n\n"), {"role": "ci", "max": "3"})


class Compute(unittest.TestCase):
    def test_idle_laptop_ci_gets_all_cores(self):
        r = cb.compute(**inputs(conf={"role": "ci"}))
        self.assertEqual(r["result"], 4)

    def test_busy_scaled_to_cores_rounded_up(self):
        # load 7.2 on 8 logical, 4 cores -> 3.6 -> 4 busy -> 0 free -> clamp 1
        r = cb.compute(**inputs(load1=7.2, conf={"role": "ci"}))
        self.assertEqual(r["busy"], 4)
        self.assertEqual(r["result"], 1)

    def test_partial_load(self):
        r = cb.compute(**inputs(load1=2.0, conf={"role": "ci"}))   # 2*4/8 = 1
        self.assertEqual((r["busy"], r["result"]), (1, 3))

    def test_ram_cap(self):
        r = cb.compute(**inputs(mem_mb=1100, conf={"role": "ci"}))   # 1100//512 = 2
        self.assertEqual((r["ram_cap"], r["result"]), (2, 2))

    def test_role_hosting_quarter(self):
        r = cb.compute(**inputs(cores=8, logical=8, conf={"role": "hosting"}))
        self.assertEqual((r["role_cap"], r["result"]), (2, 2))

    def test_role_production_is_one(self):
        r = cb.compute(**inputs(conf={"role": "production"}))
        self.assertEqual(r["result"], 1)

    def test_role_build50_half_of_all_cores(self):
        # Mac: 4 performance cores used for 'cores', 10 physical in total -> cap 5, result limited by cores
        r = cb.compute(**inputs(cores=4, logical=10, all_cores=10, conf={"role": "build50"}))
        self.assertEqual(r["role_cap"], 5)
        self.assertEqual(r["result"], 4)

    def test_conf_max_caps(self):
        r = cb.compute(**inputs(conf={"role": "ci", "max": "2"}))
        self.assertEqual(r["result"], 2)

    def test_measured_max_may_exceed_physical_cores_up_to_logical(self):
        r = cb.compute(**inputs(conf={"role": "ci", "max": "6"}))   # idle laptop 4C/8T
        self.assertEqual(r["result"], 6)

    def test_max_never_exceeds_logical_cpus(self):
        r = cb.compute(**inputs(conf={"role": "ci", "max": "16"}))
        self.assertEqual(r["result"], 8)

    def test_max_with_load_still_subtracts_busy(self):
        r = cb.compute(**inputs(load1=4.0, conf={"role": "ci", "max": "6"}))   # busy 2
        self.assertEqual(r["result"], 4)

    def test_mac_all_cores_is_perf_plus_efficiency(self):
        self.assertEqual(cb.mac_all_cores(4, 6, 10), 10)
        self.assertEqual(cb.mac_all_cores(4, None, 10), 10)   # no perflevel1: hw.physicalcpu
        self.assertEqual(cb.mac_all_cores(None, None, None, 8), 8)

    def test_no_conf_means_no_role_cap(self):
        r = cb.compute(**inputs())
        self.assertEqual(r["result"], 4)

    def test_never_below_one(self):
        r = cb.compute(**inputs(load1=99, mem_mb=10, conf={"role": "ci"}))
        self.assertEqual(r["result"], 1)

    def test_override_cpu_budget_wins(self):
        r = cb.compute(**inputs(load1=99, env={"CPU_BUDGET": "6"}))
        self.assertEqual(r["result"], 6)

    def test_override_pest_procs(self):
        r = cb.compute(**inputs(env={"PEST_PROCS": "3"}))
        self.assertEqual(r["result"], 3)

    def test_bad_override_ignored(self):
        r = cb.compute(**inputs(env={"CPU_BUDGET": "abc"}))
        self.assertEqual(r["result"], 4)

    def test_explain_lines(self):
        r = cb.compute(**inputs(conf={"role": "ci"}))
        lines = cb.explain(r).splitlines()
        self.assertEqual(len(lines), 1 + 6)
        self.assertTrue(lines[0].startswith("cores="))
        self.assertTrue(lines[-1].startswith("result="))


if __name__ == "__main__":
    unittest.main()
