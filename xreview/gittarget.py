"""Git target resolution: turn a branch name (or nothing) into a reviewable diff.

Rules (see design):
  - target = positional arg, else the current branch
  - base   = --base, else the auto-detected default branch (origin/HEAD)
  - diff   = base...target  (three-dot => diff against the merge-base, so a
             moved base never pollutes the review)
  - uncommitted working-tree changes are folded in ONLY when reviewing the
    current branch (the "review my current work" case)
  - "A..B" / "A...B" as the target is an explicit range escape hatch
"""

import subprocess
from pathlib import Path


def _git(repo, *args, check=True):
    r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def repo_root(start="."):
    try:
        return _git(start, "rev-parse", "--show-toplevel")
    except RuntimeError:
        return None


def detect_default_branch(repo):
    # Prefer the symbolic ref origin/HEAD points at.
    ref = _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", check=False)
    if ref:
        return ref.replace("refs/remotes/origin/", "")  # e.g. "main"
    for cand in ("main", "master", "develop"):
        if _git(repo, "rev-parse", "--verify", "--quiet", cand, check=False):
            return cand
    return "main"


def _base_ref_for_diff(repo, base):
    """Pick the comparable ref for `base`: prefer origin/<base> if it exists."""
    if _git(repo, "rev-parse", "--verify", "--quiet", f"origin/{base}", check=False):
        return f"origin/{base}"
    return base


def resolve(target_arg=None, base_arg=None, start="."):
    repo = repo_root(start)
    if not repo:
        raise RuntimeError("not inside a git repository")

    current = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")

    # Explicit range escape hatch.
    if target_arg and (".." in target_arg):
        diff = _git(repo, "diff", target_arg)
        files = _git(repo, "diff", "--name-only", target_arg).splitlines()
        return {
            "repo": repo, "repo_name": Path(repo).name,
            "mode": "range", "range": target_arg,
            "target_ref": target_arg, "base_ref": None, "merge_base": None,
            "is_current": False, "include_uncommitted": False,
            "diff": diff, "uncommitted_diff": "", "changed_files": files,
        }

    target_ref = target_arg or current
    base = base_arg or detect_default_branch(repo)
    base_ref = _base_ref_for_diff(repo, base)

    if not _git(repo, "rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}", check=False):
        raise RuntimeError(
            f"base '{base}' not found (resolved to '{base_ref}'). "
            f"Pass --base <branch> with a ref that exists, e.g. `git branch -a` to list them.")

    merge_base = _git(repo, "merge-base", base_ref, target_ref, check=False)
    diff = _git(repo, "diff", f"{base_ref}...{target_ref}", check=False)
    files = _git(repo, "diff", "--name-only", f"{base_ref}...{target_ref}", check=False).splitlines()

    # No merge-base means the two refs share no history — almost always a shallow
    # clone. Three-dot diff then yields an empty diff, which we must not report as
    # "nothing to review" (that hides the real problem).
    if not merge_base:
        shallow = _git(repo, "rev-parse", "--is-shallow-repository", check=False) == "true"
        hint = ("this is a shallow clone — run `git fetch --unshallow` (or fetch enough "
                "history) so a merge-base with the base exists"
                if shallow else
                f"'{base_ref}' and '{target_ref}' share no common history")
        raise RuntimeError(
            f"no merge-base between '{base_ref}' and '{target_ref}': {hint}.")

    is_current = (target_ref == current)
    uncommitted = ""
    if is_current:
        # Working tree + staged, relative to HEAD.
        uncommitted = _git(repo, "diff", "HEAD", check=False)
        unc_files = _git(repo, "diff", "--name-only", "HEAD", check=False).splitlines()
        for f in unc_files:
            if f not in files:
                files.append(f)

    return {
        "repo": repo, "repo_name": Path(repo).name,
        "mode": "branch",
        "target_ref": target_ref, "base_ref": base_ref, "merge_base": merge_base,
        "is_current": is_current, "include_uncommitted": bool(uncommitted),
        "diff": diff, "uncommitted_diff": uncommitted, "changed_files": files,
    }


def file_content(repo, ref, path, from_disk, max_lines):
    """Current content of a changed file. Disk for uncommitted; git show otherwise."""
    if from_disk:
        p = Path(repo) / path
        if not p.exists():
            return None  # deleted
        try:
            text = p.read_text(errors="replace")
        except (OSError, UnicodeDecodeError):
            return None
    else:
        r = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=str(repo),
                           capture_output=True, text=True)
        if r.returncode != 0:
            return None  # deleted at this ref
        text = r.stdout
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... [truncated, {len(lines)} lines total]"]
    return "\n".join(lines)
