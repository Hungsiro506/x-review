#!/usr/bin/env python3
"""x-review: adversarial multi-model review of a branch (PR-in-waiting).

Usage:
  x-review                      # review current branch vs its base
  x-review feature/foo          # review a specific branch
  x-review --base develop       # override the base branch
  x-review HEAD~3..HEAD         # explicit commit range
  x-review --deep               # more rounds + all configured reviewers
  x-review --skills go,concurrency --rounds 3
  x-review --explore            # let reviewers walk the live repo
"""

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

from . import config as cfg
from . import context as ctx
from . import debate as dbt
from . import gittarget, reviewers, rules, synth


def log(msg):
    print(f"  ▸ {msg}", file=sys.stderr, flush=True)


def _gather_guidance(inline, files):
    """Assemble per-run context from --context (repeatable, '-' = stdin) and
    --context-file (repeatable). Returns one string given to every reviewer."""
    parts = []
    for f in files or []:
        try:
            parts.append(Path(f).read_text(errors="replace"))
        except OSError as e:
            print(f"warning: could not read --context-file {f}: {e}", file=sys.stderr)
    for c in inline or []:
        if c == "-":
            parts.append(sys.stdin.read())
        else:
            parts.append(c)
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def main():
    ap = argparse.ArgumentParser(description="Adversarial multi-model PR/branch review.")
    ap.add_argument("target", nargs="?", help="branch name or A..B range (default: current branch)")
    ap.add_argument("--base", help="base branch (default: auto-detected origin/HEAD)")
    ap.add_argument("--rounds", type=int, help="debate rounds (default from config)")
    ap.add_argument("--deep", action="store_true", help="more rounds + all configured reviewers")
    ap.add_argument("--reviewers", help="comma-separated reviewer ids to use")
    ap.add_argument("--skills", help="comma-separated skill packs (overrides auto/repo)")
    ap.add_argument("--explore", action="store_true", help="reviewers walk the live repo (read-only)")
    ap.add_argument("--context", action="append", default=[],
                    help="free-form context/guidance for this review (repeatable; use '-' to read stdin)")
    ap.add_argument("--context-file", action="append", default=[],
                    help="file whose contents are added as context (e.g. a design doc; repeatable)")
    ap.add_argument("--rules", help="path to an extra rules YAML file for this run")
    ap.add_argument("--no-rules", action="store_true", help="disable project rule injection")
    ap.add_argument("--trust-repo-rules", action="store_true",
                    help="trust rules sourced from the repo under review (let them gate the "
                         "merge and be framed as authoritative). Off by default: repo-sourced "
                         "rules are treated as untrusted data, not instructions.")
    ap.add_argument("--list-skills", action="store_true", help="list available skill packs and exit")
    ap.add_argument("--list-rules", action="store_true", help="list resolved project rules and exit")
    ap.add_argument("-o", "--output", help="write the final report to this path too")
    args = ap.parse_args()

    try:
        config = cfg.load_config()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.list_skills:
        print("Available skill packs:", ", ".join(cfg.list_available_skills()))
        return 0

    if args.list_rules:
        if args.no_rules:
            print("Project rules are disabled (--no-rules); none would be applied.")
            return 0
        try:
            resolved = rules.load_rules(gittarget.repo_root(), args.rules)
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        if not resolved:
            print("No project rules resolved. Add YAML to ~/.config/x-review/rules/ "
                  "or your repo's .x-review.yaml. See xreview/data/rules/*.example.")
            return 0
        # Best-effort: if we can resolve the current change, show how many files
        # each rule actually matches, so a mis-globbed rule (e.g. `*.go`, which
        # does NOT cross directories) is visibly a no-op instead of silently one.
        changed = []
        try:
            changed = gittarget.resolve(args.target, args.base)["changed_files"]
        except RuntimeError:
            pass
        print(f"Resolved {len(resolved)} rule(s):")
        for r in resolved:
            sev = r.get("severity", "-")
            bm = "blocks-merge" if r.get("blocks_merge") else "-"
            hits = (f"matches={sum(1 for f in changed if rules.matches(r, f))}"
                    if changed else "matches=?")
            print(f"  {r['id']:<32} {sev:<8} {bm:<12} match={r['match']:<18} "
                  f"{hits:<12} [{r.get('_source','?')}]")
        if changed and any(not any(rules.matches(r, f) for f in changed) for r in resolved):
            print("\nNote: rules with matches=0 apply to no changed file. Remember `*` "
                  "stays within one path segment — use `**/` to cross directories "
                  "(e.g. `**/*.go`, not `*.go`).")
        return 0

    # --- Resolve git target -------------------------------------------------
    try:
        target = gittarget.resolve(args.target, args.base)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if not (target["diff"] or target["uncommitted_diff"]):
        print("Nothing to review: the diff against the base is empty.", file=sys.stderr)
        return 1

    try:
        repo_overrides = cfg.load_repo_overrides(target["repo"])
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # --- Select reviewers ---------------------------------------------------
    all_reviewers = {r["id"]: r for r in config["reviewers"]}
    if args.reviewers:
        chosen = [r.strip() for r in args.reviewers.split(",")]
    elif args.deep:
        chosen = list(all_reviewers.keys())
    else:
        chosen = repo_overrides.get("reviewers") or config["defaults"]["reviewers"]
    reviewer_cfgs = [all_reviewers[i] for i in chosen if i in all_reviewers]
    if not reviewer_cfgs:
        print(f"error: no valid reviewers in {chosen}. Available: {list(all_reviewers)}", file=sys.stderr)
        return 2

    rounds = args.rounds or (config["defaults"]["deep_rounds"] if args.deep
                             else config["defaults"]["rounds"])
    synth_kind = config["synthesizer"]["kind"]

    # --- Preflight ----------------------------------------------------------
    ok, msgs = cfg.preflight(reviewer_cfgs, synth_kind)
    for m in msgs:
        log(m.strip())
    if not ok:
        print("\nPreflight failed: a reviewer CLI above is missing or not logged in.",
              file=sys.stderr)
        available = [r["id"] for r in reviewer_cfgs if reviewers.cli_available(r["kind"])]
        if available:
            print(f"Tip: run with only what you have installed:  "
                  f"x-review --reviewers {','.join(available)}", file=sys.stderr)
        return 3

    # --- Skill packs --------------------------------------------------------
    language = ctx.dominant_language(target["changed_files"])
    cli_skills = [s.strip() for s in args.skills.split(",")] if args.skills else None
    skill_names = cfg.pick_skill_names(cli_skills, repo_overrides, config, language)
    skills_by_id = {}
    for r in reviewer_cfgs:
        names = r.get("skills", []) + [s for s in skill_names if s not in r.get("skills", [])]
        skills_by_id[r["id"]] = cfg.resolve_skills(names)

    # --- Project rules (matched to the changed files) -----------------------
    in_effect = []
    if not args.no_rules:
        try:
            all_rules = rules.load_rules(target["repo"], args.rules)
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        in_effect = rules.match_rules(all_rules, target["changed_files"])
        # Warn about loaded rules that matched nothing — usually a glob mistake,
        # otherwise they silently do nothing (e.g. `*.go` won't cross directories).
        matched_ids = {r["id"] for r in in_effect}
        for r in all_rules:
            if r["id"] not in matched_ids:
                log(f"rule '{r['id']}' (match={r['match']}) matched no changed file "
                    f"— check the glob (`*` stays in one segment; use `**/` to cross dirs)")
        # Trust boundary: rules from the repo under review are untrusted unless the
        # user opts in. Untrusted rules are framed as data and never gate the merge.
        rules.apply_trust(in_effect, trust_repo_rules=args.trust_repo_rules)
        untrusted = sum(1 for r in in_effect if not r["_trusted"])
        if untrusted:
            log(f"{untrusted} rule(s) from the repo under review treated as UNTRUSTED "
                f"(data only, no merge gate); pass --trust-repo-rules to trust them")
        rules_block = rules.render_block(in_effect)
        if rules_block:
            for rid in skills_by_id:
                skills_by_id[rid] = (skills_by_id[rid] + "\n\n" + rules_block).strip()

    # --- Per-run context / guidance ----------------------------------------
    guidance = _gather_guidance(args.context, args.context_file)

    # --- Banner -------------------------------------------------------------
    if target["mode"] == "range":
        scope = f"range {target['range']}"
    else:
        scope = f"{target['target_ref']} ⟵ {target['base_ref']}"
        if target["include_uncommitted"]:
            scope += " (+ uncommitted)"
    log(f"repo: {target['repo_name']}   scope: {scope}")
    log(f"language: {language}   skills: {', '.join(skill_names)}")
    rules_note = f"{len(in_effect)} in effect" if not args.no_rules else "disabled"
    ctx_note = "context: explore" if args.explore else "context: diff+files"
    if guidance:
        ctx_note += f" + {len(guidance)} chars guidance"
    log(f"reviewers: {', '.join(r['id'] for r in reviewer_cfgs)}   rounds: {rounds}   "
        f"{ctx_note}   rules: {rules_note}")

    context = ctx.build(target,
                        max_file_lines=config["defaults"]["max_file_lines"],
                        max_chars=config["defaults"]["max_context_chars"],
                        explore=args.explore,
                        guidance=guidance)

    # --- Debate + synthesize ------------------------------------------------
    start = time.time()
    final_state = dbt.run(reviewer_cfgs, context, rounds, args.explore,
                          target["repo"], skills_by_id, log)

    # Guard against silent failure: if every reviewer returned nothing (e.g. a CLI
    # that passed preflight but is not actually logged in), do NOT save an empty
    # "(no response)" report and exit 0 — that reads as a clean review.
    if all(not (s.get("raw") or "").strip() for s in final_state):
        print("error: every reviewer returned no output — the model CLIs likely are not "
              "authenticated (e.g. run `claude` once to /login, or check `codex`). "
              "No report saved.", file=sys.stderr)
        return 4

    report = synth.synthesize(synth_kind, final_state, log, rules=in_effect, guidance=guidance)
    elapsed = int(time.time() - start)

    # --- Persist + emit -----------------------------------------------------
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = cfg.scratch_dir(target["repo_name"], target["target_ref"] or "range")
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"{stamp}.md"
    report_path.write_text(report)
    if args.output:
        Path(args.output).write_text(report)

    log(f"done in {elapsed//60}m{elapsed%60:02d}s   saved: {report_path}")
    print("\n" + report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
