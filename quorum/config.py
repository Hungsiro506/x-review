"""Config loading, skill-pack resolution, and preflight checks.

Paths resolve in layers so the tool works both pip-installed and from source,
and so users can extend it without editing the package:

  config:  repo-local .quorum.yaml  >  user config  >  bundled default
  skills:  user skills dir  >  bundled skills

User dir defaults to ~/.config/quorum (override with QUORUM_HOME).
"""

import os
from pathlib import Path

import yaml

PKG_DIR = Path(__file__).resolve().parent
DATA_DIR = PKG_DIR / "data"
DEFAULT_CONFIG = DATA_DIR / "config.yaml"
BUNDLED_SKILLS = DATA_DIR / "skills"
SKILL_MD = DATA_DIR / "SKILL.md"

USER_DIR = Path(
    os.environ.get(
        "QUORUM_HOME",
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "quorum",
    )
)
USER_CONFIG = USER_DIR / "config.yaml"
USER_SKILLS = USER_DIR / "skills"


def load_config():
    """Bundled default config, shallow-merged with the user config if present."""
    with open(DEFAULT_CONFIG) as f:
        cfg = yaml.safe_load(f)
    if USER_CONFIG.exists():
        with open(USER_CONFIG) as f:
            user = yaml.safe_load(f) or {}
        cfg.update(user)  # top-level override (reviewers, defaults, ...)
    return cfg


def load_repo_overrides(repo):
    """Per-repo .quorum.yaml at the repo root, if present."""
    p = Path(repo) / ".quorum.yaml"
    if p.exists():
        with open(p) as f:
            return yaml.safe_load(f) or {}
    return {}


def _skill_path(name):
    """User skills dir wins over bundled."""
    for base in (USER_SKILLS, BUNDLED_SKILLS):
        p = base / f"{name}.md"
        if p.exists():
            return p
    return None


def resolve_skills(skill_names):
    """Concatenate skill-pack markdown into one block. Missing names skipped."""
    chunks = []
    for name in skill_names:
        p = _skill_path(name)
        if p:
            chunks.append(f"<!-- skill: {name} -->\n{p.read_text()}")
    return "\n\n".join(chunks)


def pick_skill_names(cli_skills, repo_overrides, config, language):
    """Order: --skills flag > .quorum.yaml > language default."""
    if cli_skills:
        return cli_skills
    if repo_overrides.get("skills"):
        return repo_overrides["skills"]
    defaults = config.get("skill_defaults", {})
    return defaults.get(language, defaults.get("default", ["general"]))


def list_available_skills():
    names = set()
    for base in (BUNDLED_SKILLS, USER_SKILLS):
        if base.exists():
            names.update(p.stem for p in base.glob("*.md"))
    return sorted(names)


def preflight(reviewer_cfgs, synth_kind):
    """Return (ok, messages). Checks CLI availability before any model call."""
    from . import reviewers
    msgs, ok = [], True
    kinds = {r["kind"] for r in reviewer_cfgs} | {synth_kind}
    for kind in sorted(kinds):
        if reviewers.cli_available(kind):
            msgs.append(f"  ✓ {kind} CLI found")
        else:
            ok = False
            hint = {
                "claude": "install Claude Code and run `claude` once to log in",
                "codex": "install the Codex CLI and authenticate",
            }.get(kind, "install and authenticate this CLI")
            msgs.append(f"  ✗ {kind} CLI NOT found — {hint}")
    return ok, msgs


def scratch_dir(repo_name, target_ref):
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in target_ref)
    return base / "quorum" / repo_name / safe
