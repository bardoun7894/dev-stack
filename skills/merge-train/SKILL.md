---
name: merge-train
description: Land several reviewed, green-or-network-red PRs in one CI run through a train-* branch (P1 tier, heavy jobs on boat), then check each PR really landed. Use when merging PRs into a repo whose CI uses train-* branches (MEDIA TGB), on "merge train", "land these PRs", "batch the PRs", "قطار", "دمج البرات".
---

# merge-train

A train is one branch `train-<date><letter>` built from main plus each PR merged at a fixed head. Its CI runs once for all of
them (train-* is P1: heavy jobs on boat). When it is green, merging the train merges every PR in it.

```
merge-train build <owner/repo> <train-branch> <pr> [<pr>...]
merge-train land  <owner/repo> <train-pr>
```

`bin/merge-train` (on PATH after install.sh).

## Rules

1. Only PRs whose review has no open P0/P1 (one review + one fix round), and whose last red run failed on the network only.
2. `build` sets every PR in the train to draft. A review bot or agent (pr-review bot, Cursor) pushes fix commits after tests;
   draft pauses it. Commits pushed after `build` are not in the train.
3. `build` skips a PR that conflicts and says so. Two trains may run at once if they share no files.
4. A red train: read the failing job. A network failure (DNS, download, git fetch timeout): `gh run rerun <id> --failed`.
   A test failure: take that PR out (rebuild without it) and send the failure to its implementer; `gh pr ready <n>` to un-draft it.
5. `land` merges only when ci-ok is SUCCESS, with `--match-head-commit`. It then lists each PR. "NOT landed" means the PR head moved
   after `build`: read the new commits, and put the PR in the next train. Exit 1 when any PR did not land.
6. After landing a batch of code PRs: one `tokyo-deploy ask` for the batch, not one per train.

Why (2026-11-16 night, MEDIA TGB): #776 got two bot commits after its train was built, one of them fixing a real gap; without
the draft and the land check it would have looked merged while the fix was still open.
