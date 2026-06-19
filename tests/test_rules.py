"""Unit tests for the project-rules layer. No model calls, no network."""

import textwrap
from pathlib import Path

from xreview import debate, rules, synth


def test_glob_double_star_crosses_dirs():
    r = {"match": "**/domain/**/*.go", "id": "x", "text": "t"}
    assert rules.matches(r, "internal/domain/user/svc.go")
    assert rules.matches(r, "domain/user.go")
    assert not rules.matches(r, "internal/handler/h.go")


def test_glob_single_star_stays_in_segment():
    r = {"match": "src/*.go", "id": "x", "text": "t"}
    assert rules.matches(r, "src/main.go")
    assert not rules.matches(r, "src/pkg/main.go")


def test_brace_alternation():
    r = {"match": "**/{usecase,handler}/**/*.go", "id": "x", "text": "t"}
    assert rules.matches(r, "a/usecase/x.go")
    assert rules.matches(r, "a/handler/x.go")
    assert not rules.matches(r, "a/repo/x.go")


def test_match_rules_selects_in_effect_only():
    rs = [
        {"id": "go", "match": "**/*.go", "text": "t"},
        {"id": "py", "match": "**/*.py", "text": "t"},
    ]
    eff = rules.match_rules(rs, ["a/b.go"])
    assert [r["id"] for r in eff] == ["go"]
    assert eff[0]["_files"] == ["a/b.go"]


def test_load_rules_layering_and_dedup(tmp_path):
    repo = tmp_path
    (repo / ".x-review").mkdir()
    (repo / ".x-review" / "rules").mkdir()
    (repo / ".x-review" / "rules" / "team.yaml").write_text(textwrap.dedent("""
        rules:
          - id: dup
            match: "**/*.go"
            severity: low
            text: from-repo-dir
    """))
    (repo / ".x-review.yaml").write_text(textwrap.dedent("""
        rules:
          - id: dup
            match: "**/*.go"
            severity: high
            text: from-inline
          - id: extra
            match: "**/*.py"
            text: extra-rule
    """))
    loaded = {r["id"]: r for r in rules.load_rules(str(repo))}
    assert "extra" in loaded
    # inline .x-review.yaml is a later layer than the repo rules dir, so it wins
    assert loaded["dup"]["text"] == "from-inline"
    assert loaded["dup"]["severity"] == "high"


def test_render_block_is_empty_when_no_rules():
    assert rules.render_block([]) == ""


def test_render_block_lists_rules():
    block = rules.render_block([
        {"id": "r1", "match": "x", "text": "do the thing", "severity": "high",
         "blocks_merge": True},
    ])
    assert "r1" in block and "blocks merge" in block and "do the thing" in block


def test_finding_schema_and_debate_rules_mention_rule_id():
    assert "rule_id" in debate.FINDING_SCHEMA
    assert "rule_id" in debate.RULES


def test_synth_prompt_includes_rules_section():
    s = synth.SYNTH_PROMPT.format(n=1, reviews="(x)", rules="## Project rules\n(none)")
    assert "Project rules" in s


def _state(*rule_ids):
    return [{"id": "claude", "raw": "",
             "parsed": {"findings": [{"title": "t", "rule_id": rid} for rid in rule_ids]}}]


def test_enforce_blocks_merge_overrides_verdict():
    in_effect = [{"id": "r1", "match": "x", "text": "no infra", "blocks_merge": True}]
    out = "Some report.\n\nMerge decision: APPROVE"
    fixed = synth._enforce_rules(out, _state("r1"), in_effect, lambda *_: None)
    assert "Merge decision: REQUEST CHANGES" in fixed
    assert "Enforced rule blockers" in fixed
    assert "`r1`" in fixed


def test_enforce_ignores_non_blocking_rule():
    in_effect = [{"id": "r1", "match": "x", "text": "thin", "blocks_merge": False}]
    out = "Merge decision: APPROVE"
    fixed = synth._enforce_rules(out, _state("r1"), in_effect, lambda *_: None)
    assert fixed == out  # untouched


def test_enforce_ignores_bogus_rule_id():
    in_effect = [{"id": "r1", "match": "x", "text": "t", "blocks_merge": True}]
    out = "Merge decision: APPROVE"
    # reviewer cites a rule id that is not in effect -> must not gate
    fixed = synth._enforce_rules(out, _state("nope"), in_effect, lambda *_: None)
    assert fixed == out


def test_enforce_no_rules_is_noop():
    out = "Merge decision: APPROVE"
    assert synth._enforce_rules(out, _state("r1"), [], lambda *_: None) == out
