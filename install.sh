#!/usr/bin/env bash
# Install x-review: the `x-review` command + a user-level Claude Code skill.
# Works in a virtualenv, in a normal user environment, and on "externally
# managed" Pythons (PEP 668) via a launcher-shim fallback. Idempotent.
set -euo pipefail

TOOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="${HOME}/.claude/skills/x-review"
BIN_DIR="${HOME}/.local/bin"

# In a virtualenv/conda env, `pip --user` is illegal, so drop it there.
IN_VENV="$(python3 -c 'import sys; print(int(sys.prefix != getattr(sys, "base_prefix", sys.prefix)))' 2>/dev/null || echo 0)"
if [ "${IN_VENV}" = "1" ]; then USERFLAG=""; else USERFLAG="--user"; fi

installed=""

# 1a) Preferred: editable pip install (gives the console entry point).
if python3 -m pip install ${USERFLAG} -e "${TOOL_DIR}" -q 2>/dev/null; then
  installed="pip"
# 1b) pipx, if available.
elif command -v pipx >/dev/null 2>&1 && pipx install -e "${TOOL_DIR}" 2>/dev/null; then
  installed="pipx"
else
  # 1c) Fallback: a launcher shim that runs from source. Needs pyyaml available
  #     to the python3 that the shim will use.
  echo "pip/pipx install did not succeed — installing a launcher shim instead."
  if ! python3 -c "import yaml" 2>/dev/null; then
    python3 -m pip install ${USERFLAG} -q pyyaml 2>/dev/null \
      || python3 -m pip install ${USERFLAG} --break-system-packages -q pyyaml
  fi
  mkdir -p "${BIN_DIR}"
  cat > "${BIN_DIR}/x-review" <<EOF
#!/usr/bin/env bash
exec python3 "${TOOL_DIR}/review.py" "\$@"
EOF
  chmod +x "${BIN_DIR}/x-review"
  installed="shim"
fi
echo "✓ CLI installed via: ${installed}"

# 2) User-level Claude Code skill (available in every repo).
mkdir -p "${SKILL_DIR}"
cp "${TOOL_DIR}/xreview/data/SKILL.md" "${SKILL_DIR}/SKILL.md"
echo "✓ Claude skill installed: ${SKILL_DIR}/SKILL.md"

# 3) Locate the installed command for the PATH hint and smoke test.
ENTRY="$(command -v x-review 2>/dev/null || true)"
if [ -z "${ENTRY}" ]; then
  for cand in "${BIN_DIR}/x-review" "$(python3 -m site --user-base 2>/dev/null)/bin/x-review"; do
    [ -x "${cand}" ] && { ENTRY="${cand}"; break; }
  done
fi

# 4) Post-install smoke test — fail loudly rather than report a false success.
#    This catches the classic "installed but pyyaml missing" venv failure.
if [ -n "${ENTRY}" ] && "${ENTRY}" --list-skills >/dev/null 2>&1; then
  echo "✓ Post-install check passed: x-review runs."
else
  echo "" >&2
  echo "✗ Install finished but x-review does not run. Diagnostic output:" >&2
  { [ -n "${ENTRY}" ] && "${ENTRY}" --list-skills; } 2>&1 | sed 's/^/    /' >&2 || true
  echo "  Try a direct editable install from this directory:" >&2
  echo "      python3 -m pip install -e \"${TOOL_DIR}\"" >&2
  exit 1
fi

# 5) PATH hint if the command is installed but not yet on PATH.
if ! command -v x-review >/dev/null 2>&1; then
  HINT="$(dirname "${ENTRY}")"
  echo ""
  echo "⚠ 'x-review' is installed at ${ENTRY} but not on your PATH. Add to your shell rc:"
  echo "    export PATH=\"${HINT}:\${PATH}\""
fi

echo ""
echo "Done. Try:  cd <any-repo> && x-review --list-skills"
