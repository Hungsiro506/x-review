"""The adversarial debate loop.

  Round 1: each reviewer reviews independently.
  Round r: each reviewer sees all reviewers' previous-round findings
           (anonymized as Reviewer A/B/...) and revises — conceding only with
           concrete code evidence, raising new issues as they appear.
  Stops early when findings stabilize across a round (convergence).
"""

import random
import string
from concurrent.futures import ThreadPoolExecutor

from . import reviewers

FINDING_SCHEMA = (
    'Output ONLY a JSON object, no prose:\n'
    '{\n'
    '  "summary": "one-paragraph overall take",\n'
    '  "findings": [\n'
    '    {"title": "short bug title", "severity": "high|medium|low",\n'
    '     "location": "file:line or function", "confidence": "high|medium|low",\n'
    '     "rule_id": "id of a matched project rule, or null if none applies",\n'
    '     "explanation": "what is wrong and why, citing the code"}\n'
    '  ]\n'
    '}\n'
    'If you find nothing, return an empty findings array.'
)

RULES = (
    "Rules:\n"
    "- Base every claim on the provided code. Cite specific lines/functions.\n"
    "- Review the change as submitted; do not assume a later fix exists.\n"
    "- Do not concede a point to end the debate. Defend a correct position with evidence.\n"
    "- Change your stance only when shown irrefutable code-based evidence — not confidence.\n"
    "- If another reviewer's argument reveals a new issue, raise it.\n"
    "- If a finding matches a listed project rule, set its rule_id and cite the rule. "
    "Project rules add criteria; still report issues no rule covers.\n"
)


def _round1_prompt(persona, skills_text, context):
    return (
        f"{skills_text}\n\n"
        f"You are {persona}.\n\n{RULES}\n{context}\n\n{FINDING_SCHEMA}"
    )


def _render_findings(parsed, raw):
    if parsed and parsed.get("findings") is not None:
        lines = [f"Summary: {parsed.get('summary', '')}"]
        for fnd in parsed["findings"]:
            rule = f", rule {fnd['rule_id']}" if fnd.get("rule_id") else ""
            lines.append(
                f"- [{fnd.get('severity', '?')}] {fnd.get('title', '')} "
                f"({fnd.get('location', '?')}, confidence {fnd.get('confidence', '?')}{rule}): "
                f"{fnd.get('explanation', '')}"
            )
        return "\n".join(lines)
    return (raw or "(no response)")[:4000]


def _debate_prompt(persona, skills_text, context, others_block):
    return (
        f"{skills_text}\n\n"
        f"You are {persona}.\n\n{RULES}\n{context}\n\n"
        f"## Other reviewers' findings from the previous round (anonymized)\n"
        f"{others_block}\n\n"
        f"Revise your review in light of the above. {FINDING_SCHEMA}"
    )


def _signature(parsed):
    if not parsed:
        return None
    return tuple(sorted((f.get("title", "") or "").strip().lower()
                        for f in parsed.get("findings", [])))


def run(reviewer_cfgs, context, rounds, explore, repo, skills_by_id, log):
    """Drive the debate. Returns the final per-reviewer state list."""
    # state[id] = {"cfg":..., "raw":..., "parsed":...}
    state = {r["id"]: {"cfg": r, "raw": "", "parsed": {}} for r in reviewer_cfgs}

    def call(rid, prompt):
        cfg = state[rid]["cfg"]
        raw = reviewers.invoke(cfg["kind"], prompt, repo=repo, explore=explore)
        state[rid]["raw"] = raw
        state[rid]["parsed"] = reviewers.parse_json(raw)

    # Round 1 — independent, in parallel.
    log(f"round 1/{rounds}: {len(reviewer_cfgs)} reviewers (independent)")
    with ThreadPoolExecutor(max_workers=len(reviewer_cfgs)) as pool:
        for r in reviewer_cfgs:
            prompt = _round1_prompt(r["persona"], skills_by_id[r["id"]], context)
            pool.submit(call, r["id"], prompt)

    prev_sigs = {rid: _signature(state[rid]["parsed"]) for rid in state}

    for rnd in range(2, rounds + 1):
        # Stable anonymization for this round.
        letters = list(string.ascii_uppercase)
        ids = [r["id"] for r in reviewer_cfgs]
        random.shuffle(ids)
        alias = {rid: f"Reviewer {letters[i]}" for i, rid in enumerate(ids)}

        log(f"round {rnd}/{rounds}: broadcast + revise")

        def call_round(rid):
            r = state[rid]["cfg"]
            others = [f"### {alias[oid]}\n{_render_findings(state[oid]['parsed'], state[oid]['raw'])}"
                      for oid in state if oid != rid]
            prompt = _debate_prompt(r["persona"], skills_by_id[rid], context, "\n\n".join(others))
            call(rid, prompt)

        with ThreadPoolExecutor(max_workers=len(reviewer_cfgs)) as pool:
            list(pool.map(call_round, list(state.keys())))

        new_sigs = {rid: _signature(state[rid]["parsed"]) for rid in state}
        if all(new_sigs[rid] is not None and new_sigs[rid] == prev_sigs[rid] for rid in state):
            log(f"converged after round {rnd} (findings stable)")
            break
        prev_sigs = new_sigs

    return [{"id": rid, **state[rid]} for rid in state]
