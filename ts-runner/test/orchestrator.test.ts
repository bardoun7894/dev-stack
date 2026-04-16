import { describe, it, expect } from "vitest";
import {
  planDispatch,
  countIndependentUnits,
} from "../src/orchestrator.js";
import { pickModel } from "../src/types.js";

describe("pickModel", () => {
  it("maps trivial → haiku", () => {
    expect(pickModel("trivial")).toBe("claude-haiku-4-5");
  });
  it("maps simple → sonnet", () => {
    expect(pickModel("simple")).toBe("claude-sonnet-4-6");
  });
  it("maps medium → sonnet", () => {
    expect(pickModel("medium")).toBe("claude-sonnet-4-6");
  });
  it("maps hard → opus", () => {
    expect(pickModel("hard")).toBe("claude-opus-4-6");
  });
});

describe("countIndependentUnits", () => {
  it("returns 0 for no packets", () => {
    expect(countIndependentUnits([])).toBe(0);
  });

  it("returns 1 for a single packet", () => {
    expect(
      countIndependentUnits([
        {
          role: "frontend-engineer",
          label: "a",
          tasks: ["t"],
          filesInScope: ["a.ts"],
          complexity: "simple",
        },
      ]),
    ).toBe(1);
  });

  it("counts two non-overlapping packets as NIU=2", () => {
    expect(
      countIndependentUnits([
        {
          role: "frontend-engineer",
          label: "fe",
          tasks: ["t"],
          filesInScope: ["src/ui.ts"],
          complexity: "simple",
        },
        {
          role: "backend-engineer",
          label: "be",
          tasks: ["t"],
          filesInScope: ["src/api.ts"],
          complexity: "simple",
        },
      ]),
    ).toBe(2);
  });

  it("collapses packets with overlapping files into NIU=1", () => {
    expect(
      countIndependentUnits([
        {
          role: "frontend-engineer",
          label: "fe",
          tasks: ["t"],
          filesInScope: ["src/shared.ts"],
          complexity: "simple",
        },
        {
          role: "backend-engineer",
          label: "be",
          tasks: ["t"],
          filesInScope: ["src/shared.ts"],
          complexity: "simple",
        },
      ]),
    ).toBe(1);
  });

  it("collapses packets with declared dependencies", () => {
    expect(
      countIndependentUnits([
        {
          role: "backend-engineer",
          label: "schema",
          tasks: ["t"],
          filesInScope: ["db.ts"],
          complexity: "simple",
        },
        {
          role: "frontend-engineer",
          label: "ui",
          tasks: ["t"],
          filesInScope: ["ui.ts"],
          complexity: "simple",
          dependencies: ["schema"],
        },
      ]),
    ).toBe(1);
  });
});

describe("planDispatch", () => {
  it("returns solo mode for NIU=1", () => {
    const plan = planDispatch([
      {
        role: "frontend-engineer",
        label: "a",
        tasks: ["t"],
        filesInScope: ["a.ts"],
        complexity: "simple",
      },
    ]);
    expect(plan.dispatchMode).toBe("solo");
    expect(plan.niu).toBe(1);
    expect(plan.packets).toHaveLength(1);
  });

  it("returns fanout mode for NIU=2", () => {
    const plan = planDispatch([
      {
        role: "frontend-engineer",
        label: "fe",
        tasks: ["t"],
        filesInScope: ["ui.ts"],
        complexity: "simple",
      },
      {
        role: "backend-engineer",
        label: "be",
        tasks: ["t"],
        filesInScope: ["api.ts"],
        complexity: "simple",
      },
    ]);
    expect(plan.dispatchMode).toBe("fanout");
    expect(plan.niu).toBe(2);
  });

  it("returns fanout mode for NIU=4", () => {
    const plan = planDispatch(
      Array.from({ length: 4 }).map((_, i) => ({
        role: "qa-engineer" as const,
        label: `p${i}`,
        tasks: ["t"],
        filesInScope: [`file${i}.ts`],
        complexity: "simple" as const,
      })),
    );
    expect(plan.dispatchMode).toBe("fanout");
  });

  it("returns batched mode for NIU=5-8", () => {
    const plan = planDispatch(
      Array.from({ length: 6 }).map((_, i) => ({
        role: "qa-engineer" as const,
        label: `p${i}`,
        tasks: ["t"],
        filesInScope: [`file${i}.ts`],
        complexity: "simple" as const,
      })),
    );
    expect(plan.dispatchMode).toBe("batched");
    expect(plan.niu).toBe(6);
  });

  it("rejects NIU ≥ 9 as too big", () => {
    const plan = planDispatch(
      Array.from({ length: 10 }).map((_, i) => ({
        role: "qa-engineer" as const,
        label: `p${i}`,
        tasks: ["t"],
        filesInScope: [`file${i}.ts`],
        complexity: "simple" as const,
      })),
    );
    expect(plan.dispatchMode).toBe("reject");
  });

  it("assigns haiku for trivial, opus for hard", () => {
    const plan = planDispatch([
      {
        role: "frontend-engineer",
        label: "a",
        tasks: ["lookup"],
        filesInScope: ["a.ts"],
        complexity: "trivial",
      },
      {
        role: "backend-engineer",
        label: "b",
        tasks: ["migrate"],
        filesInScope: ["b.ts"],
        complexity: "hard",
      },
    ]);
    expect(plan.packets[0]?.model).toBe("claude-haiku-4-5");
    expect(plan.packets[1]?.model).toBe("claude-opus-4-6");
  });
});
