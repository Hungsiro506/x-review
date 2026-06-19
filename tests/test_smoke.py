"""Unit smoke tests — no model calls, no network."""

import subprocess
import tempfile
from pathlib import Path

from xreview import config, context, gittarget, reviewers, synth


def test_config_loads_and_has_reviewers():
    cfg = config.load_config()
    assert cfg["reviewers"], "config must define reviewers"
    assert cfg["defaults"]["reviewers"], "config must define default reviewers"
    assert cfg["synthesizer"]["kind"]


def test_bundled_skills_present():
    skills = config.list_available_skills()
    assert "general" in skills


def test_synth_prompt_formats():
    s = synth.SYNTH_PROMPT.format(n=2, reviews="(x)")
    assert "SECTION 1" in s and "SECTION 2" in s and "Merge decision" in s


def test_parse_json_handles_fenced_output():
    assert reviewers.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert reviewers.parse_json('prose {"a": 2} more') == {"a": 2}
    assert reviewers.parse_json("not json") == {}


def test_language_detection():
    assert context.dominant_language(["a.go", "b.go", "c.py"]) == "go"
    assert context.dominant_language([]) == "default"


def test_gittarget_resolves_a_real_repo():
    with tempfile.TemporaryDirectory() as d:
        run = lambda *a: subprocess.run(["git", *a], cwd=d, check=True,
                                        capture_output=True)
        run("init", "-q")
        run("config", "user.email", "t@t.co")
        run("config", "user.name", "t")
        Path(d, "f.txt").write_text("hello\n")
        run("add", "-A")
        run("commit", "-qm", "init")
        run("branch", "-m", "main")
        run("checkout", "-qb", "feature")
        Path(d, "f.txt").write_text("hello\nworld\n")
        run("add", "-A")
        run("commit", "-qm", "change")

        t = gittarget.resolve(None, "main", start=d)
        assert t["target_ref"] == "feature"
        assert t["base_ref"] in ("main", "origin/main")
        assert "world" in t["diff"]
        assert "f.txt" in t["changed_files"]
