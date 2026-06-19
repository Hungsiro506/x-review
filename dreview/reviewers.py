"""Invoke model CLIs as reviewers.

Each reviewer runs in a clean environment:
  - CLAUDECODE unset (so a nested claude-code session is allowed)
  - permissions/sandbox bypassed (reviewers are read-only; they never write)
  - cwd = the repo (only when --explore), else a throwaway temp dir
"""

import json
import os
import re
import subprocess
import tempfile

TIMEOUT = 900  # 15 min per reviewer call


def cli_available(kind):
    exe = {"claude": "claude", "codex": "codex"}.get(kind, kind)
    return subprocess.run(["which", exe], capture_output=True).returncode == 0


def _clean_env():
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    return env


def invoke(kind, prompt, repo=None, explore=False):
    """Run one reviewer/synth call. Returns raw stdout text ('' on failure)."""
    env = _clean_env()
    cwd = repo if (explore and repo) else tempfile.mkdtemp(prefix="dreview_")
    created_tmp = not (explore and repo)

    if kind == "claude":
        cmd = ["claude", "-p", "-", "--dangerously-skip-permissions"]
        inp = prompt
    elif kind == "codex":
        cmd = ["codex", "exec", "--json", "--dangerously-bypass-approvals-and-sandbox", "-"]
        inp = prompt
    else:
        raise ValueError(f"unknown reviewer kind: {kind}")

    try:
        r = subprocess.run(cmd, input=inp, capture_output=True, text=True,
                           timeout=TIMEOUT, env=env, cwd=cwd)
    except subprocess.TimeoutExpired:
        return ""
    finally:
        if created_tmp:
            try:
                os.rmdir(cwd)
            except OSError:
                pass

    if r.returncode != 0:
        return ""

    out = r.stdout.strip()
    if kind == "codex" and out:
        out = _parse_codex_jsonl(out)
    return out


def _parse_codex_jsonl(out):
    parts = []
    for line in out.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
            item = ev.get("item", {})
            if ev.get("type") == "item.completed" and item.get("type") == "agent_message" and item.get("text"):
                parts.append(item["text"])
        except json.JSONDecodeError:
            parts.append(line)
    return "\n".join(parts) if parts else out


def parse_json(response):
    """Extract a JSON object from a model response (handles ``` fences, prose)."""
    if not response:
        return {}
    text = response.strip()
    block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if block:
        text = block.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}
