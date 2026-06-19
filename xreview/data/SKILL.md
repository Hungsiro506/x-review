---
name: x-review
description: Multi-model code review of a git branch. Gathers context from the current Claude session (a design doc, a ticket, focus instructions, whatever the user provided) and runs the local x-review CLI, which has Claude and Codex debate the diff and merge it into one ranked verdict. Use when the user says "review my branch", "review this PR", "x-review", "review <branch>", or wants a second/third opinion before opening or merging a PR.
---

# x-review

This skill makes the current Claude session the master driver: you gather the
context, then hand it to the `x-review` CLI, which runs the real cross-vendor
committee (Claude + Codex by default). The CLI is the engine. Do NOT
re-implement the debate as Claude subagents; that would lose the cross-vendor
diversity that makes the review work.

## The workflow

1. **Settle the target.** Which branch (default: current), which base if not the
   default branch.
2. **Gather context from this session.** Pull together anything the user gave you
   that the reviewers should know: a design doc or spec, the ticket/PR
   description, focus instructions ("watch the redis counter race"), constraints,
   links you already read. Write it to a temp file, for example
   `/tmp/x-review-context.md`.
3. **Run the CLI with that context.** Every committee member receives the same
   context block:

   ```bash
   x-review <branch> --context-file /tmp/x-review-context.md
   ```

   Other useful flags: `--base <branch>`, `--deep` (more rounds + reviewers),
   `--rules <file>` (codified team rules), `--skills go,concurrency`,
   `--explore` (reviewers walk the repo). You can also pass short guidance inline
   with `--context "focus on X"` instead of a file.
4. **Stream progress** from the CLI's stderr while it runs (it takes minutes).
5. **Relay the report.** The final ranked Markdown (manager summary + tech-lead
   detail + merge decision) prints on stdout and is saved under
   `~/.cache/x-review/<repo>/<branch>/`.
6. **Act on findings.** This is where the session earns its keep: when the user
   picks a finding ("fix #2"), implement the fix in the working tree, then offer
   to re-run `x-review` to confirm it is resolved.

## Notes

- If the user gave no extra context, just run `x-review <branch>` without
  `--context-file`. Context is optional, not required.
- Clean up the temp context file when done.
- Do not post anything to GitHub unless the user explicitly asks.
