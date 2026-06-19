# debate-review

> Adversarial multi-model code review for **any** repo. Point it at a branch;
> Claude and Codex review it independently, **debate each other** across rounds
> to cover each other's blind spots, then a synthesizer merges everything into
> one ranked, two-audience report.

```bash
cd ~/your/repo
debate-review          # reviews the current branch vs its base
```

## Why I built this

A single model is a single point of view, and I kept getting contradictory
reviews — one model would flag a data race, another would call the same code
clean. So I stopped trusting any one model and started making them argue.

The gain isn't from one model being smarter; it's that models have **different
blind spots**. One walks the call chain and lives in the boring error paths;
another is terse but catches the one off-by-one everyone else skimmed past.
Forcing them to defend or revise their claims against each other — with every
point grounded in actual code — surfaces far more than running any of them
alone, and the things multiple models independently agree on are the things
worth acting on first.

`debate-review` is my opinionated take on that workflow: one command you run on
your own branches before opening or merging a PR. It works in three stages:

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

**Install the tool**

```bash
git clone https://github.com/brvu/debate-review
cd debate-review
./install.sh          # pip install -e . + installs the Claude Code skill
```

Or just:

```bash
pip install --user -e .
```

A preflight check verifies every reviewer's CLI is present and authenticated
*before* any model is called, so you fail in seconds, not minutes.

## Quick start

```bash
cd ~/any/repo

debate-review                  # current branch vs auto-detected base (+ uncommitted work)
debate-review feature/foo      # a specific branch
debate-review --base develop   # override the base branch
debate-review HEAD~3..HEAD     # explicit commit range
debate-review --deep           # more rounds + all configured reviewers
debate-review --skills go,concurrency --rounds 3
debate-review --explore        # let reviewers walk the live repo (read-only)
debate-review --list-skills
```

From **Claude Code**, the installed skill lets you run `/debate-review` and then
act on a finding ("fix #2") interactively — that's where Claude/Cursor earns its
keep, on top of the review.

The final Markdown report prints to stdout and is saved under
`~/.cache/debate-review/<repo>/<branch>/<timestamp>.md`. **Nothing is written
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
  `~/.config/debate-review/skills/<name>.md` (or the bundled `dreview/data/skills/`),
  then reference it via `--skills`, a repo-local `.debate-review.yaml`, or
  `skill_defaults` in config. Skill packs are how you teach reviewers your
  architecture standards, domain rules, or recurring-bug patterns.
- **Add a reviewer / persona:** add an entry under `reviewers:` in config. If its
  CLI is invoked differently, add a branch in `dreview/reviewers.py`.
- **Per-repo defaults:** commit a `.debate-review.yaml` at the repo root:

  ```yaml
  reviewers: [claude, codex]
  skills: [general, concurrency]
  ```

- **User config override:** put a `config.yaml` in `~/.config/debate-review/` to
  override reviewers/defaults globally without editing the package.

## How it works (architecture)

```
debate-review <branch>
  │
  ├─ gittarget   branch → diff (merge-base), changed files, uncommitted scope
  ├─ context     diff + full content of changed files; language detection
  ├─ debate      round 1 independent → broadcast (anonymized) → revise → … (convergence-stop)
  ├─ synth       cluster + rank + two-audience report + merge decision
  └─ saved to ~/.cache/debate-review/...
```

| File | Responsibility |
|------|----------------|
| `dreview/cli.py` | argument parsing, orchestration |
| `dreview/gittarget.py` | branch→diff resolution |
| `dreview/context.py` | context pack, language detection |
| `dreview/reviewers.py` | model CLI invocation + output parsing |
| `dreview/debate.py` | the multi-round adversarial loop |
| `dreview/synth.py` | final merge / ranking / two-audience report |
| `dreview/config.py` | config + skill resolution + preflight |
| `dreview/data/config.yaml` | reviewers, defaults, skill routing |
| `dreview/data/skills/*.md` | knowledge packs |

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
