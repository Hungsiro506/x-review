# x-review

> **x-review-based code review.** Point it at a branch; a committee of model
> reviewers (different vendors) reviews it, **debates to agreement**, and hands
> you one ranked verdict — not three walls of opinion.

```bash
cd ~/your/repo
x-review          # convene the committee on the current branch
```

## Why I built this

Code review carries two costs, and they pull against each other. The first is
the **risk of being wrong** — a lone model, like a lone reviewer, confidently
rubber-stamps code that merely *looks* right; I kept getting contradictory
reviews where one model flagged a data race and another called the same code
clean. The second is **cognitive debt**: the mental load you take on to hold an
unfamiliar change in your head. That debt is what makes review slow, shallow,
and easy to rush — and naively throwing more reviewers (or more model output) at
the problem only deepens it.

x-review is a bet that a **committee beats a soloist** on *both* costs at once.

- **Correctness — through debate.** Instead of trusting one model, x-review
  convenes a panel of *different* model vendors and makes them argue, every
  claim grounded in actual code. Models have different blind spots; forcing them
  to defend or revise against each other surfaces far more than any one alone.
  A finding earns your attention by the committee converging on it —
  **agreement is the signal, disagreement is a flag**, not noise.
- **Less cognitive debt — through distillation.** A debate could easily produce
  *more* to read. x-review does the opposite: it collapses the whole argument into
  a ranked verdict (Blocker→Low) with two audiences — a jargon-free **manager
  summary** and a deep **tech-lead detail** sharing the same numbering — plus a
  single merge decision. You read the committee's conclusion, not the
  transcript. Your job shrinks from *"understand everything"* to *"act on what
  the x-review agreed matters most."*

`x-review` is my opinionated take on that workflow: one command you run on your own
branches before opening or merging a PR. It works in three stages:

1. **Independent review** — each reviewer reviews the diff (+ changed-file
   context) on its own.
2. **Debate** — every reviewer sees the others' findings (anonymized) and
   revises: conceding only with concrete code evidence, raising new issues.
3. **Synthesis** — one model clusters the findings, ranks them
   Blocker→Low, and writes a **manager summary** and a **tech-lead detail**
   section with the same numbering, plus a merge decision.

It is **open-source-first and vendor-neutral**: a "reviewer" is just a model CLI
+ a persona + a stack of markdown **skill packs**. Add knowledge by dropping in a
`.md`; add a model by adding a config entry.

## Install

**Prerequisites**

- Python 3.10+
- `git`
- The reviewer CLIs you enable, installed and authenticated:
  - [`claude`](https://claude.com/claude-code) (Claude Code)
  - [`codex`](https://developers.openai.com/codex/cli) (Codex CLI)

**Install the tool** (recommended — works everywhere)

```bash
git clone https://github.com/Hungsiro506/x-review
cd x-review
bash install.sh       # installs the `x-review` command + the Claude Code skill
```

`install.sh` tries a normal `pip install -e .`, then `pipx`, and finally falls
back to a self-contained launcher shim — so it works even on the
"externally-managed" Python (PEP 668) you get from Homebrew or recent Debian/
Ubuntu, where a bare `pip install` is blocked. If it prints a PATH hint, add the
shown directory to your `PATH`.

**Install directly with pip** (only if your Python isn't externally-managed):

```bash
pip install --user -e .            # may fail with "externally-managed-environment"
# on a PEP 668 Python, use one of:  pipx install -e .   |   pip install -e . --break-system-packages
```

A preflight check verifies every reviewer's CLI is present and authenticated
*before* any model is called, so you fail in seconds, not minutes.

## Quick start

```bash
cd ~/any/repo

x-review                  # current branch vs auto-detected base (+ uncommitted work)
x-review feature/foo      # a specific branch
x-review --base develop   # override the base branch
x-review HEAD~3..HEAD     # explicit commit range
x-review --deep           # more rounds + all configured reviewers
x-review --skills go,concurrency --rounds 3
x-review --explore        # let reviewers walk the live repo (read-only)
x-review --list-skills
```

From **Claude Code**, the installed skill lets you run `/x-review` and then
act on a finding ("fix #2") interactively — that's where Claude/Cursor earns its
keep, on top of the review.

The final Markdown report prints to stdout and is saved under
`~/.cache/x-review/<repo>/<branch>/<timestamp>.md`. **Nothing is written
into the repo under review.**

## How target resolution works

- **target** = the branch arg, else the current branch.
- **base** = `--base`, else the auto-detected default branch (`origin/HEAD`).
- **diff** = `base...target` (merge-base three-dot — a moved base never pollutes
  the review).
- **uncommitted** working-tree changes are folded in **only** when reviewing the
  current branch (the "review my current work" case).

## Extending it

This is the whole point of the design — extend without touching code:

- **Add knowledge (a skill pack):** drop a markdown file in your user skills dir
  `~/.config/x-review/skills/<name>.md` (or the bundled `xreview/data/skills/`),
  then reference it via `--skills`, a repo-local `.x-review.yaml`, or
  `skill_defaults` in config. Skill packs are how you teach reviewers your
  architecture standards, domain rules, or recurring-bug patterns.
- **Add a reviewer / persona:** add an entry under `reviewers:` in config. If its
  CLI is invoked differently, add a branch in `xreview/reviewers.py`.
- **Per-repo defaults:** commit a `.x-review.yaml` at the repo root:

  ```yaml
  reviewers: [claude, codex]
  skills: [general, concurrency]
  ```

- **User config override:** put a `config.yaml` in `~/.config/x-review/` to
  override reviewers/defaults globally without editing the package.

## How it works (architecture)

```
x-review <branch>
  │
  ├─ gittarget   branch → diff (merge-base), changed files, uncommitted scope
  ├─ context     diff + full content of changed files; language detection
  ├─ debate      round 1 independent → broadcast (anonymized) → revise → … (convergence-stop)
  ├─ synth       cluster + rank + two-audience report + merge decision
  └─ saved to ~/.cache/x-review/...
```

| File | Responsibility |
|------|----------------|
| `xreview/cli.py` | argument parsing, orchestration |
| `xreview/gittarget.py` | branch→diff resolution |
| `xreview/context.py` | context pack, language detection |
| `xreview/reviewers.py` | model CLI invocation + output parsing |
| `xreview/debate.py` | the multi-round adversarial loop |
| `xreview/synth.py` | final merge / ranking / two-audience report |
| `xreview/config.py` | config + skill resolution + preflight |
| `xreview/data/config.yaml` | reviewers, defaults, skill routing |
| `xreview/data/skills/*.md` | knowledge packs |

## Cost & limitations

- Debate is **quadratic in rounds** (each round re-broadcasts prior findings).
  The default is deliberately cheap: 2 reviewers, 2 rounds, convergence-stop.
  `--deep` is the expensive opt-in.
- Models are **non-deterministic**; treat a single run as directional, not a
  proof. Agreement across reviewers is the signal to trust.
- Reviewer diversity is what makes debate work. With one vendor you get less of
  it — add a second vendor's CLI, or differentiate via skill packs/personas.

## License

MIT — see [LICENSE](LICENSE).
