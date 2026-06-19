---
name: x-review
description: Adversarial multi-model code review of the current branch (or a named branch) as a PR-in-waiting. Claude and Codex review independently, debate across rounds to cover each other's blind spots, then a synthesizer merges findings into one ranked report with debate-derived confidence. Use when the user says "review my branch", "review this PR", "debate review", "review <branch>", or wants a second/third opinion on changes before opening or merging a PR.
---

# x-review

Runs the local `x-review` CLI, which orchestrates an adversarial debate
between multiple model CLIs (Claude + Codex by default) over the diff of a
branch against its base, then synthesizes one ranked review.

## How to run it

The engine is the CLI — do NOT re-implement the debate here. From the repo the
user wants reviewed, run (it runs long; show progress):

```bash
x-review                       # current branch vs auto-detected base
x-review <branch>              # a specific branch
x-review --base <branch>       # override the base
x-review --deep                # 5 rounds, all configured reviewers
x-review --skills go,concurrency
x-review --explore             # reviewers walk the live repo (read-only)
```

Stream the CLI's stderr progress to the user. When it finishes, the final
Markdown report is printed on stdout and saved under
`~/.cache/x-review/<repo>/<branch>/`.

## Your job around the CLI

1. Confirm the target with the user if ambiguous (which branch, which base).
2. Run the CLI and relay the synthesized findings.
3. This is where you add value over the raw CLI: when the user picks a finding
   ("fix #2"), implement the fix in the working tree, then optionally re-run
   `x-review` to confirm it's resolved.

Do not post anything to GitHub unless the user explicitly asks.
