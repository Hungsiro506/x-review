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
from . import gittarget, rules, synth


def log(msg):
    print(f"  ▸ {msg}", file=sys.stderr, flush=True)


def main():
    ap = argparse.ArgumentParser(description="Adversarial multi-model PR/branch review.")
    ap.add_argument("target", nargs="?", help="branch name or A..B range (default: current branch)")
    ap.add_argument("--base", help="base branch (default: auto-detected origin/HEAD)")
    ap.add_argument("--rounds", type=int, help="debate rounds (default from config)")
    ap.add_argument("--deep", action="store_true", help="more rounds + all configured reviewers")
    ap.add_argument("--reviewers", help="comma-separated reviewer ids to use")
    ap.add_argument("--skills", help="comma-separated skill packs (overrides auto/repo)")
    ap.add_argument("--explore", action="store_true", help="reviewers walk the live repo (read-only)")
    ap.add_argument("--rules", help="path to an extra rules YAML file for this run")
    ap.add_argument("--no-rules", action="store_true", help="disable project rule injection")
    ap.add_argument("--list-skills", action="store_true", help="list available skill packs and exit")
    ap.add_argument("--list-rules", action="store_true", help="list resolved project rules and exit")
    ap.add_argument("-o", "--output", help="write the final report to this path too")
    args = ap.parse_args()

    config = cfg.load_config()

    if args.list_skills:
        print("Available skill packs:", ", ".join(cfg.list_available_skills()))
        return 0

    if args.list_rules:
        resolved = rules.load_rules(gittarget.repo_root(), args.rules)
        if not resolved:
            print("No project rules resolved. Add YAML to ~/.config/x-review/rules/ "
                  "or your repo's .x-review.yaml. See xreview/data/rules/*.example.")
            return 0
        print(f"Resolved {len(resolved)} rule(s):")
        for r in resolved:
            sev = r.get("severity", "-")
            bm = "blocks-merge" if r.get("blocks_merge") else "-"
            print(f"  {r['id']:<32} {sev:<8} {bm:<12} match={r['match']}  [{r.get('_source','?')}]")
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

    repo_overrides = cfg.load_repo_overrides(target["repo"])

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
        print("\nPreflight failed — fix the missing CLIs above and retry.", file=sys.stderr)
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
        all_rules = rules.load_rules(target["repo"], args.rules)
        in_effect = rules.match_rules(all_rules, target["changed_files"])
        rules_block = rules.render_block(in_effect)
        if rules_block:
            for rid in skills_by_id:
                skills_by_id[rid] = (skills_by_id[rid] + "\n\n" + rules_block).strip()

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
    log(f"reviewers: {', '.join(r['id'] for r in reviewer_cfgs)}   rounds: {rounds}   "
        f"context: {'explore' if args.explore else 'diff+files'}   rules: {rules_note}")

    context = ctx.build(target,
                        max_file_lines=config["defaults"]["max_file_lines"],
                        max_chars=config["defaults"]["max_context_chars"],
                        explore=args.explore)

    # --- Debate + synthesize ------------------------------------------------
    start = time.time()
    final_state = dbt.run(reviewer_cfgs, context, rounds, args.explore,
                          target["repo"], skills_by_id, log)
    report = synth.synthesize(synth_kind, final_state, log, rules=in_effect)
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
