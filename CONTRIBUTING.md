# Contributing

Thanks for helping improve quorum. It's small and means to stay that way.

## Setup

```bash
git clone https://github.com/brvu/quorum
cd quorum
pip install --user -e .
python -m pytest -q
```

## Ground rules

- **Standard library + pyyaml only.** New dependencies need a strong
  justification — easy install is a feature.
- **Keep the stage boundaries** (`cli → gittarget → context → debate → synth`).
  See [CLAUDE.md](CLAUDE.md) for which file owns what.
- **Reviewers are read-only** on the repo under review. Never write to it.
- **Vendor-neutral.** No model name outside `reviewers.py` / `data/config.yaml`.
- Tests must not call models or the network.

## Good first contributions

- **New skill packs** (`quorum/data/skills/*.md`) — review lenses for a
  language, framework, or class of bug. Highest-leverage, lowest-risk.
- **New reviewer adapters** in `reviewers.py` for other model CLIs.
- **Better context gathering** (call-chain / symbol extraction) in `context.py`.

## Submitting

1. Branch off `main`.
2. Add/adjust tests where it makes sense.
3. Run `python -m pytest -q` and a real `--rounds 1` smoke test.
4. Open a PR describing the change and its motivation. (Dogfood:
   `quorum` your own branch first.)
