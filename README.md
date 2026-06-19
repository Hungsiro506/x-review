# x-review

Multi-model code review for a git branch. It runs more than one AI model over
your changes, has them debate and back every claim with code, and gives you one
ranked review instead of several conflicting ones.

```bash
cd ~/your/repo
x-review
```

## Why

I used AI models to review a pull request and got contradictory answers: Claude
flagged a data race, another model called the same code clean. So I stopped
trusting any single model and went looking at the numbers.

A benchmark ran five flagship models (Claude, Gemini, Codex, Qwen, MiniMax)
against 15 real pull requests that were each merged and then reverted or
hotfixed, so every PR had a known bug to score against. On the harder bugs (the
ones that need surrounding context or system-level understanding):

- the best single model caught about 53%,
- five models debating each other for five rounds caught about 80%,
- the hardest, system-level bugs went from spotty to 100% caught,
- the biggest jump was on ordinary mid-level bugs: 3 of 10 for one model alone,
  7 of 10 for the debating group,
- two models together already reached roughly 91% of the five-model result,
  which is why x-review defaults to two.

Debate works because models have different blind spots. One reads the call chain
and the boring error paths; another is terse but catches the off-by-one everyone
skimmed. Making them argue, with every claim tied to a specific line, finds more
than running any one of them on its own. The findings that more than one model
agrees on are the ones worth your time.

There is a second problem: a debate can produce more to read, not less. So the
last step does the opposite. It collapses the whole argument into a ranked list
(Blocker to Low), a short plain-language summary, a detailed section for whoever
fixes the code, and one merge decision. You read the conclusion, not the
back-and-forth.

## How it works

Three steps:

1. Each model reviews the diff and the changed files on its own.
2. Each model sees the others' findings, anonymized, and revises. It can only
   drop a point with code evidence, and it raises anything new it notices.
3. One model merges the results, removes duplicates, ranks them, and writes the
   final report with a merge decision. A deterministic pass then enforces any
   codified [rules](#rules--codified-standards-caught-every-time) you have set:
   a confirmed `blocks_merge` violation forces the verdict to `REQUEST CHANGES`.

A reviewer is just a model CLI, a short persona, and some markdown "skill packs"
of review knowledge. Add a skill by dropping in a file; add a model by adding a
config entry. The tool is vendor-neutral; nothing is hardcoded to one model.
Project **rules** add path-scoped team standards on top — see
[Rules](#rules--codified-standards-caught-every-time).

## Install

You need Python 3.10+, `git`, and the reviewer CLIs you want to use, installed
and logged in:

- [`claude`](https://claude.com/claude-code) (Claude Code)
- [`codex`](https://developers.openai.com/codex/cli) (Codex CLI)

Then:

```bash
git clone https://github.com/Hungsiro506/x-review
cd x-review
bash install.sh       # installs the `x-review` command + the Claude Code skill
```

`install.sh` tries `pip install -e .`, then `pipx`, and finally a self-contained
launcher shim, so it still works on the "externally-managed" Python (PEP 668)
you get from Homebrew or recent Debian/Ubuntu, where a bare `pip install` is
blocked. If it prints a PATH hint, add the shown directory to your `PATH`.

To install with pip directly (only if your Python is not externally-managed):

```bash
pip install --user -e .
# on a PEP 668 Python use:  pipx install -e .   or   pip install -e . --break-system-packages
```

A preflight check confirms each reviewer's CLI is present and logged in before
any model runs, so you find out in seconds, not minutes.

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
x-review --list-rules     # show resolved project rules (no model calls)
x-review --rules team.yaml --rounds 3   # add codified rules for this run
x-review --no-rules       # ignore project rules for this run
```

From Claude Code you can run `/x-review`, then ask it to fix a finding ("fix
#2") in the same session.

The report prints to stdout and is also saved under
`~/.cache/x-review/<repo>/<branch>/<timestamp>.md`. Nothing is written into the
repo being reviewed.

## How target resolution works

- `target` is the branch argument, otherwise the current branch.
- `base` is `--base`, otherwise the auto-detected default branch (`origin/HEAD`).
- the diff is `base...target` (merge-base three-dot), so a base that has moved
  ahead does not pollute the review.
- uncommitted working-tree changes are included only when reviewing the current
  branch, which is the "review what I'm working on" case.

## Extending it

You can extend the tool without touching its code:

- **Add a skill pack.** Put a markdown file in `~/.config/x-review/skills/<name>.md`
  (or the bundled `xreview/data/skills/`) and reference it with `--skills`, a
  repo-local `.x-review.yaml`, or `skill_defaults` in the config. Skill packs are
  how you teach reviewers your architecture rules, domain knowledge, or the bugs
  that keep coming back.
- **Add a rule.** Drop a YAML file in `~/.config/x-review/rules/<name>.yaml` (or
  your repo's `.x-review/rules/`) to codify a path-scoped team standard. See
  [Rules](#rules--codified-standards-caught-every-time). No code change.
- **Add a reviewer.** Add an entry under `reviewers:` in the config. If its CLI
  is called differently from the others, add a branch in `xreview/reviewers.py`.
- **Set per-repo defaults.** Commit a `.x-review.yaml` at the repo root:

  ```yaml
  reviewers: [claude, codex]
  skills: [general, concurrency]
  ```

- **Override globally.** Put a `config.yaml` in `~/.config/x-review/` to change
  reviewers and defaults without editing the package.

## Rules — codified standards, caught every time

Debate is a **recall** bet: more models, arguing, catch more of what any one
model misses. But debate has nothing to say about the standards your team has
already written down — the layering boundary, the banned import, the rule
everyone knows but a model has no way to know. That is a **precision** problem,
and it is exactly what Alibaba's open-source [Open Code Review][ocr] (OCR) is
good at: deterministic, path-scoped rule checks.

Rules port OCR's precision lever into x-review **without** adopting its "let the
rule overrule the model" stance. The result is both bets at once: the debate
still finds what no rule anticipated, and codified rules are caught every time.

[ocr]: https://github.com/alibaba/open-code-review

A rule is a skill pack that knows which files it applies to, plus optional
grading metadata:

```yaml
rules:
  - id: go-domain-no-infra
    match: "**/domain/**/*.go"     # ** crosses dirs, * within a segment, {a,b} alternates
    severity: high                 # optional: blocker|high|medium|low
    blocks_merge: true             # optional
    text: "Domain layer must not import infrastructure packages (db, kafka, http clients)."
```

### What you get

- **A shared rubric for the debate.** Matched rules are injected into every
  reviewer next to the skill packs. A finding stops being "I think this is bad"
  and becomes "this violates `go-domain-no-infra`, here is the line" — much
  harder to wave away, much easier for another reviewer to independently
  confirm. So rules make agreement a stronger signal and convergence faster.
- **Determinism where you have written the standard down.** A confirmed
  `blocks_merge` violation gates the merge **in code**, not by asking the model
  nicely. After synthesis, x-review checks which rules reviewers actually cited:
  if a `blocks_merge` rule was cited, the **Merge decision** is forced to
  `REQUEST CHANGES` and an **Enforced rule blockers** section is appended. The
  model writes the narrative; the rule decides the gate.
- **No hallucinated gate.** A `rule_id` a reviewer cites that is not actually in
  effect (made up or stale) is dropped and logged, so a fabricated rule can
  never block a merge.
- **Precise, not lucky.** A layering rule fires only on the files it matches, so
  a `kafka` import in the domain layer gets flagged consistently instead of when
  a model happens to notice it.

### The one guardrail

Rules **add** criteria; they never gate or silence a reviewer. Reviewers must
still report anything no rule covers, and a finding with no `rule_id` is just as
valid. That single line is what separates "rules strengthen the committee" (us)
from "rules replace the committee" (OCR's default). Code only ever *adds* a
blocker on a confirmed hit — it never downgrades or suppresses a finding.

### Where rules come from

Four layers, later layers winning on the same id (mirrors OCR):

1. `--rules <file>` on the command line
2. repo `.x-review.yaml` (`rules:` list) and `.x-review/rules/*.yaml`
3. user `~/.config/x-review/rules/*.yaml`
4. bundled `xreview/data/rules/*.yaml` (ships empty, so nothing fires until you add a rule)

```bash
x-review --list-rules     # show every resolved rule, its source, and match — no model calls
x-review --rules team.yaml  # add a rules file for this run
x-review --no-rules       # turn the layer off for this run
```

Rules need no install step and no code change: drop a YAML file in
`~/.config/x-review/rules/` or your repo's `.x-review/rules/` and it is picked
up. A copy-me starter is in `xreview/data/rules/axon-layered.yaml.example`.

## Architecture

```
x-review <branch>
  │
  ├─ gittarget   branch → diff (merge-base), changed files, uncommitted scope
  ├─ context     diff + full content of changed files; language detection
  ├─ rules       resolve + path-match codified team rules; inject into reviewers
  ├─ debate      round 1 independent → broadcast (anonymized) → revise → … (convergence-stop)
  ├─ synth       cluster + rank + two-audience report + merge decision; enforce blocks_merge rules
  └─ saved to ~/.cache/x-review/...
```

| File | Responsibility |
|------|----------------|
| `xreview/cli.py` | argument parsing, orchestration |
| `xreview/gittarget.py` | branch to diff resolution |
| `xreview/context.py` | context pack, language detection |
| `xreview/reviewers.py` | model CLI invocation + output parsing |
| `xreview/debate.py` | the multi-round debate loop |
| `xreview/synth.py` | final merge, ranking, two-audience report, deterministic rule enforcement |
| `xreview/rules.py` | rule loading (4 layers), glob matching, prompt rendering |
| `xreview/config.py` | config + skill resolution + preflight |
| `xreview/data/config.yaml` | reviewers, defaults, skill routing |
| `xreview/data/skills/*.md` | knowledge packs |
| `xreview/data/rules/*.yaml` | bundled rules (ships empty) + `.example` starter |

## What it costs

x-review trades money and time for correctness, so the cheap path is the default
and the expensive path is something you ask for.

Each run makes `(reviewers × rounds) + 1` model calls. The default of 2
reviewers and 2 rounds is about 5 calls. `--deep` (3 reviewers, 5 rounds) is
about 16, and each later round also carries the earlier findings in its prompt,
so token cost grows faster than the call count. The debate stops early once the
findings stop changing, so you often pay less than that.

For a sense of wall-clock time: a tiny diff at default settings finished in
under a minute, and a real 24-file change at 2 rounds took about 11 minutes. The
dollar cost is whatever the underlying model CLIs (Claude Code, Codex) charge on
your plan; x-review just calls them and adds nothing.

The benchmark above is the reason to spend more when it matters. A single pass
finds the obvious and agreed-upon bugs (around 53%). The deeper modes (more
rounds, more vendors, `--explore`) are what reach the system-level bugs and push
detection toward 80%. Use them on the changes that are worth it.

## Limitations

- Model output is not deterministic. Treat one run as a strong signal, not
  proof. Trust the findings that more than one reviewer reaches independently.
  The exception is rules: once a `blocks_merge` rule is cited as violated, the
  merge gate is enforced in code, so that part of the verdict is repeatable.
- Rules raise precision only where you have written the standard down. They do
  not replace the debate — whether a rule is *violated* is still a model
  judgment cited from the code; x-review only makes the *consequence*
  deterministic.
- The gains come from reviewers being different. With a single vendor you get
  less of that, so add a second vendor's CLI or vary the skill packs and
  personas.
- The benchmark behind the numbers was 15 PRs from one Go/C++ project. The
  trend (debate beats a single model, models have different blind spots) is the
  durable part; the exact percentages are not a promise.

## Credits

The multi-vendor debate idea and the benchmark numbers come from a public
code-review benchmark and write-up. x-review is an independent reimplementation
of that idea as a local CLI. (Article link to be added.)

The **rules** layer adapts the precision model of Alibaba's open-source
[Open Code Review][ocr] — path-scoped, deterministic rule checks with a
four-layer config — and folds it into the debate so codified standards are
enforced without overruling the reviewers.

## License

MIT. See [LICENSE](LICENSE).
