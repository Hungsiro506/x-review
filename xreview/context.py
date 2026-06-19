"""Build the context pack handed to every reviewer.

Default (cheap, reproducible): the diff + the full current content of each
changed file. `--explore` skips bundling file content and instead lets the
reviewer walk the repo itself (richer on system-level bugs, slower/costlier).
"""

from . import gittarget

CODE_EXT = {
    ".go": "go", ".py": "python", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp",
    ".h": "cpp", ".hpp": "cpp", ".ts": "ts", ".tsx": "ts", ".js": "js",
    ".java": "java", ".rs": "rust", ".rb": "ruby", ".c": "c",
}


def dominant_language(changed_files):
    counts = {}
    for f in changed_files:
        for ext, lang in CODE_EXT.items():
            if f.endswith(ext):
                counts[lang] = counts.get(lang, 0) + 1
    if not counts:
        return "default"
    return max(counts, key=counts.get)


def build(target, max_file_lines, max_chars, explore=False, guidance=""):
    """Return the shared context block string.

    `guidance` is free-form per-run context from the author (design intent, focus
    areas, a linked spec). It is placed first so every reviewer reads it before
    the diff, and every reviewer receives the same text.
    """
    # Guidance gets its own budget (up to half) so a large design doc can never
    # starve the diff and file contents, which are truncated separately below.
    guidance_block = ""
    if guidance and guidance.strip():
        g = guidance.strip()
        gbudget = max_chars // 2
        if len(g) > gbudget:
            g = g[:gbudget] + "\n... [guidance truncated to fit budget]"
        guidance_block = (
            "## Author's context and guidance for this review\n"
            "The author of this change provided the following context. Treat any "
            "stated design intent as the spec to check the diff against, and honor "
            "any focus areas. This guidance narrows where to look; it does not stop "
            "you from reporting other issues you find.\n\n"
            f"{g}\n\n"
        )

    parts = []
    parts.append("## Change under review")
    if target["mode"] == "range":
        parts.append(f"Range: `{target['range']}`")
    else:
        parts.append(f"Base: `{target['base_ref']}`  →  Target: `{target['target_ref']}`")
        if target["merge_base"]:
            parts.append(f"Merge-base: `{target['merge_base'][:12]}`")
        if target["include_uncommitted"]:
            parts.append("> NOTE: includes UNCOMMITTED working-tree changes on the current branch.")
    parts.append(f"Files changed: {len(target['changed_files'])}")
    parts.append("")

    parts.append("## Diff (committed range)")
    parts.append("```diff")
    parts.append(target["diff"] or "(empty)")
    parts.append("```")

    if target.get("uncommitted_diff"):
        parts.append("\n## Uncommitted changes (working tree vs HEAD)")
        parts.append("```diff")
        parts.append(target["uncommitted_diff"])
        parts.append("```")

    if explore:
        parts.append(
            "\n## Repo access\n"
            "You have READ-ONLY access to the repository at the current working "
            "directory. Walk call chains, open related files, and read tests as "
            "needed. Do NOT modify any files."
        )
    else:
        parts.append("\n## Full current content of changed files")
        from_disk = target.get("include_uncommitted", False)
        ref = target.get("target_ref")
        for f in target["changed_files"]:
            content = gittarget.file_content(target["repo"], ref, f, from_disk, max_file_lines)
            if content is None:
                continue
            lang = next((l for e, l in CODE_EXT.items() if f.endswith(e)), "")
            parts.append(f"\n### {f}")
            parts.append(f"```{lang}")
            parts.append(content)
            parts.append("```")

    rest = "\n".join(parts)
    budget = max_chars - len(guidance_block)
    if len(rest) > budget:
        rest = rest[:budget] + "\n\n... [context truncated to fit budget]"
    return guidance_block + rest
