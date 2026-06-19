# CLAUDE.md — working on the debate-review codebase

Guidance for Claude (or any agent) writing code **in this repo**. This is about
building the tool, not about the reviews it produces.

## What this project is

A small, dependency-light Python CLI that orchestrates an **adversarial debate**
between multiple model CLIs to review a git branch, then synthesizes one ranked
report. Vendor-neutral and extensible by config + markdown skill packs. Keep it
that way — resist coupling to any one model or to heavy frameworks.

## Architecture (where things go)

The pipeline is a clean stage sequence; respect the boundaries:

```
cli.py → gittarget → context → debate → synth → saved report
```

- **`gittarget.py`** — all git/branch/diff logic. Nothing else shells out to git.
- **`context.py`** — builds the prompt context pack + language detection. No model calls.
- **`reviewers.py`** — the ONLY place that invokes model CLIs and parses their
  output. Add a new vendor here (one branch in `invoke()`), not elsewhere.
- **`debate.py`** — the round loop, anonymized broadcast, convergence check.
  Owns reviewer-facing prompt assembly (RULES + finding schema).
- **`synth.py`** — the final merge/ranking and the two-audience report prompt.
  This is the only place the manager/tech-lead OUTPUT format lives.
- **`config.py`** — config + skill resolution + preflight. Owns all path layering.

If a change touches two stages, it's usually a sign the boundary is wrong —
stop and reconsider.

## Hard rules

1. **Read-only on the repo under review.** Reviewers must never write to the
   target repo. Artifacts go to `~/.cache/debate-review/...` only.
2. **Preflight before spend.** Any new external dependency (a CLI, an API) must
   be checked in `config.preflight` so failures surface in seconds.
3. **Vendor-neutral core.** No model name hardcoded outside `reviewers.py` and
   `data/config.yaml`. Personas/skills are data, not code.
4. **Extensible without code edits.** Adding knowledge = a new `skills/*.md`.
   Adding a reviewer = a config entry (+ at most one `reviewers.py` branch).
   If a feature requires editing core code to add knowledge, redesign it.
5. **Clean env for nested agents.** Spawned CLIs run with `CLAUDECODE` unset and
   permissions/sandbox bypassed (they're read-only). Don't inherit the target
   repo's MCP/permission config into a reviewer.
6. **Cost awareness.** Debate is quadratic in rounds. Keep the default cheap
   (2 reviewers, 2 rounds, convergence-stop); expensive behavior goes behind
   `--deep` or an explicit flag.

## Conventions

- Standard library + `pyyaml` only. Do not add dependencies without a strong
  reason; this tool's value is being trivial to install.
- Subprocess calls use lists (no `shell=True`) where practical, with timeouts.
- Be defensive parsing model output — it may be wrapped in ``` fences or prose.
  Reuse `reviewers.parse_json`; don't reinvent.
- Match the existing terse, commented style. Module docstrings explain the
  "why," not just the "what."
- User-facing progress goes to **stderr** via `cli.log`; the report goes to
  **stdout**. Keep that split.

## Testing

```bash
pip install -e .
python -m pytest -q            # unit tests (no model calls)
debate-review --list-skills    # smoke: config + skills load
```

Unit tests must not call models or hit the network. For end-to-end, run against
a throwaway git repo with a planted bug and `--rounds 1 --reviewers claude`.

## Common tasks

- **Add a skill pack:** create `dreview/data/skills/<name>.md` (a focused review
  lens). Optionally add it to `skill_defaults` in `data/config.yaml`. No code.
- **Add a reviewer/persona:** add an entry under `reviewers:` in
  `data/config.yaml`. If the CLI invocation differs from claude/codex, add a
  branch in `reviewers.invoke()` and `cli_available()`.
- **Change the report format:** edit `synth.SYNTH_PROMPT` only.
- **Change reviewer behavior / finding fields:** edit `debate.RULES` and
  `debate.FINDING_SCHEMA` together, and update `_render_findings`.

## Don't

- Don't write into the target repo or its git history.
- Don't hardcode `main` as the base — use the auto-detected default branch.
- Don't diff against the raw base tip — always merge-base (`base...target`).
- Don't post to GitHub or any external service unless explicitly asked.
