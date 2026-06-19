"""Synthesize the final debate state into one ranked, deduped review."""

from . import reviewers

SYNTH_PROMPT = """You are a senior staff engineer producing the FINAL review. Below are independent reviews of the same code change from {n} reviewers after an adversarial debate. Merge them into ONE review with TWO clearly separated audiences. Do not merge the two audiences.

## How to merge (do this first)
- Cluster findings that describe the SAME underlying issue, even if worded differently. One merged finding per real issue.
- Do NOT invent issues no reviewer raised. If reviewers disagreed, weigh the code-based evidence, not confidence.
- For each merged finding determine: severity, whether it blocks merge, and whether it is NEW in this change or pre-existing.
- Severity ladder (rank worst-first): Blocker > High > Medium > Low.
  - Blocker = data loss/corruption, security, or the feature failing at its core purpose. Must fix before merge.
  - High = correctness/operability issue; fix before relying on / rolling out.
  - Medium = real but bounded; clean up soon.
  - Low = minor, cheap, or cosmetic.
- Be calibrated: do not inflate severity; if something is valid but low-impact, say so plainly.
- Use the SAME numbering across both sections so a manager and tech lead can both say "issue #3" and mean the same thing.
- Project rules (below) are codified team criteria. A finding confirmed to violate a rule is concrete, not speculative: rank it accordingly and tag it with its rule id in the tech-lead detail. If a violated rule is marked "blocks merge", treat it as a blocker in the merge decision. Findings that match no rule are still valid; do not down-rank them for lacking a rule.
{rules}

## SECTION 1: MANAGER SUMMARY
Audience: a smart manager with little system/technical context.
- No jargon. Pick ONE consistent real-world analogy for the whole system and reuse it for every issue.
- Lead with a 2-3 sentence bottom line: what's the risk, what should gate the release, what can wait.
- Then a ranked list, worst-first. For EACH item, 3 short lines: what we expect to happen (plain language); what actually happens (and whether it's silent/unexpected); why it matters (customer/business impact + cost of leaving it; state if it blocks release).
- No code. A few sentences per item. ~1 page max.

## SECTION 2: TECH LEAD DETAIL
Audience: a tech lead who knows the system. Same worst-first order, SAME numbering as Section 1. For EACH finding:
- **Title — severity — blocks merge? — new or pre-existing**
- **Flagged by:** which reviewers raised it (agreement) and the debate confidence (higher when reviewers independently agreed or evidence is strong; lower if a single reviewer or speculative).
- **Location:** file:line (+ a short code snippet if available).
- **Expected vs actual behavior:** precise, referencing the design intent where relevant.
- **Why this is the wrong pattern:** the concrete mechanism and failure mode (race, ordering, unbounded growth, divergence from spec, etc.).
- **Cost of the current approach** — score each Low/Med/High with a one-line justification: Runtime/operational; Maintainability; Extensibility; Readability.
- **Better approach:** concrete fix or pattern with a short code/pseudo-code sketch, AND its honest adoption trade-offs (what it costs to adopt) — not just "do the opposite."
- **Test gap (if any):** the test that would have caught this; note assertion-free or tautological tests.

## Style
- Specific and falsifiable; mechanism + line over hand-waving.
- If a finding depends on a downstream guarantee not visible here, say what must be confirmed and by whom rather than asserting.
- Note reviewer disagreements and who was more convincing.
- End with a **Merge decision:** APPROVE / COMMENT / REQUEST CHANGES, plus the minimal checklist of blockers to clear.

## Reviews
{reviews}

Output GitHub-flavored Markdown with exactly the two sections above (headed `=== SECTION 1: MANAGER SUMMARY ===` and `=== SECTION 2: TECH LEAD DETAIL ===`), then the Merge decision line.
"""


def _rules_text(in_effect):
    if not in_effect:
        return "## Project rules\n(none in effect for this change)"
    lines = ["## Project rules in effect for this change"]
    for r in in_effect:
        sev = f" [{r['severity']}]" if r.get("severity") else ""
        bm = " (blocks merge)" if r.get("blocks_merge") else ""
        lines.append(f"- `{r['id']}`{sev}{bm}: {r['text']}")
    return "\n".join(lines)


def synthesize(synth_kind, final_state, log, rules=None):
    blocks = []
    for s in final_state:
        parsed, raw = s["parsed"], s["raw"]
        if parsed and parsed.get("findings") is not None:
            import json
            body = json.dumps(parsed, indent=2)
        else:
            body = (raw or "(no response)")[:6000]
        blocks.append(f"### Reviewer: {s['id']}\n{body}")

    prompt = SYNTH_PROMPT.format(n=len(final_state), reviews="\n\n".join(blocks),
                                 rules=_rules_text(rules or []))
    log("synthesizing final report")
    out = reviewers.invoke(synth_kind, prompt)
    return out or _fallback(final_state)


def _fallback(final_state):
    """If the synthesizer fails, dump raw reviews so nothing is lost."""
    lines = ["# Debate review (raw — synthesizer unavailable)\n"]
    for s in final_state:
        lines.append(f"## {s['id']}\n\n{s['raw'] or '(no response)'}\n")
    return "\n".join(lines)
