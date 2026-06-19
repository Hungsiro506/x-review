"""Project rules: fine-grained, path-matched review criteria.

A rule is a skill pack that knows which files it applies to, plus optional
severity/blocks_merge metadata. Rules ADD criteria to the debate: matched rules
are injected into every reviewer, and a finding can cite a rule id as evidence.
They never gate or silence a reviewer; anything a rule does not cover is still
fair game, and a finding without a rule id is just as valid.

Sources resolve in four layers (later wins on the same id):
  1. an explicit --rules file
  2. repo .x-review.yaml (`rules:` list) and .x-review/rules/*.yaml
  3. user ~/.config/x-review/rules/*.yaml
  4. bundled xreview/data/rules/*.yaml  (ships empty)
"""

import re
from pathlib import Path

import yaml

from . import config as cfg


# --- glob matching (** crosses dirs, * within a segment, {a,b} alternates) ---

def _expand_braces(pattern):
    m = re.search(r"\{([^{}]*)\}", pattern)
    if not m:
        return [pattern]
    pre, post = pattern[:m.start()], pattern[m.end():]
    out = []
    for opt in m.group(1).split(","):
        out.extend(_expand_braces(pre + opt + post))
    return out


def _glob_to_regex(glob):
    res, i, n = "", 0, len(glob)
    while i < n:
        if glob[i:i + 3] == "**/":
            res += "(?:.*/)?"   # zero or more directories
            i += 3
        elif glob[i:i + 2] == "**":
            res += ".*"
            i += 2
        elif glob[i] == "*":
            res += "[^/]*"
            i += 1
        elif glob[i] == "?":
            res += "[^/]"
            i += 1
        else:
            res += re.escape(glob[i])
            i += 1
    return re.compile("^" + res + "$")


def matches(rule, path):
    """Does this rule's match glob apply to this file path?"""
    for g in _expand_braces(rule.get("match", "")):
        if _glob_to_regex(g).match(path):
            return True
    return False


# --- loading ----------------------------------------------------------------

def _load_file(path, source):
    try:
        data = yaml.safe_load(Path(path).read_text())
    except (OSError, yaml.YAMLError):
        return []
    items = data.get("rules", data) if isinstance(data, dict) else data
    out = []
    for r in items or []:
        if isinstance(r, dict) and r.get("id") and r.get("match") and r.get("text"):
            r = dict(r)
            r.setdefault("_source", source)
            out.append(r)
    return out


def load_rules(repo, cli_file=None):
    """Merge rules from all four layers, dedup by id (later layer wins)."""
    merged = {}

    def add(rules):
        for r in rules:
            merged[r["id"]] = r

    # 1 (lowest) bundled, 2 user, 3 repo dir + inline, 4 cli (highest)
    for base, src in ((cfg.BUNDLED_RULES, "bundled"), (cfg.USER_RULES, "user")):
        if base.exists():
            for f in sorted(base.glob("*.yaml")) + sorted(base.glob("*.yml")):
                add(_load_file(f, src))

    if repo:
        repo_rules_dir = Path(repo) / ".x-review" / "rules"
        if repo_rules_dir.exists():
            for f in sorted(repo_rules_dir.glob("*.yaml")) + sorted(repo_rules_dir.glob("*.yml")):
                add(_load_file(f, "repo"))
        overrides = cfg.load_repo_overrides(repo)
        inline = overrides.get("rules")
        if isinstance(inline, list):
            add([{**r, "_source": "repo:.x-review.yaml"} for r in inline
                 if isinstance(r, dict) and r.get("id") and r.get("match") and r.get("text")])

    if cli_file:
        add(_load_file(cli_file, f"cli:{cli_file}"))

    return list(merged.values())


def match_rules(rules, changed_files):
    """Rules in effect for this change: those matching at least one changed file."""
    in_effect = []
    for r in rules:
        hit = [f for f in changed_files if matches(r, f)]
        if hit:
            r = dict(r)
            r["_files"] = hit
            in_effect.append(r)
    return in_effect


def render_block(in_effect):
    """The rules block injected into each reviewer's prompt."""
    if not in_effect:
        return ""
    lines = [
        "## Project rules in effect for this change",
        "These are codified team criteria for the files under review. If a finding "
        "corresponds to one of these rules, set its `rule_id` and cite the rule as "
        "evidence. These rules ADD criteria; you must still report any issue they "
        "do not cover, and a finding without a rule id is equally valid.",
        "",
    ]
    for r in in_effect:
        sev = f" [{r['severity']}]" if r.get("severity") else ""
        bm = " (blocks merge)" if r.get("blocks_merge") else ""
        lines.append(f"- `{r['id']}`{sev}{bm}: {r['text']}")
    return "\n".join(lines)
