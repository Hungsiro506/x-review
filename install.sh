#!/usr/bin/env bash
# Install debate-review: the `debate-review` command + a user-level Claude Code
# skill. Tries pip, then pipx, then a no-pip launcher fallback (for PEP 668
# "externally-managed" Pythons). Idempotent — safe to re-run.
set -euo pipefail

TOOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="${HOME}/.claude/skills/debate-review"
BIN_DIR="${HOME}/.local/bin"

installed=""

# 1a) Preferred: editable pip install (gives the console entry point).
if python3 -m pip install --user -e "${TOOL_DIR}" -q 2>/dev/null; then
  installed="pip"
# 1b) pipx, if available.
elif command -v pipx >/dev/null 2>&1 && pipx install -e "${TOOL_DIR}" 2>/dev/null; then
  installed="pipx"
else
  # 1c) Fallback: a launcher shim that runs from source. Requires pyyaml.
  echo "pip/pipx install unavailable (e.g. PEP 668) — installing a launcher shim."
  python3 -c "import yaml" 2>/dev/null || python3 -m pip install --user --break-system-packages -q pyyaml
  mkdir -p "${BIN_DIR}"
  cat > "${BIN_DIR}/debate-review" <<EOF
#!/usr/bin/env bash
exec python3 "${TOOL_DIR}/review.py" "\$@"
EOF
  chmod +x "${BIN_DIR}/debate-review"
  installed="shim"
fi
echo "✓ CLI installed via: ${installed}"

# 2) User-level Claude Code skill (available in every repo).
mkdir -p "${SKILL_DIR}"
cp "${TOOL_DIR}/dreview/data/SKILL.md" "${SKILL_DIR}/SKILL.md"
echo "✓ Claude skill installed: ${SKILL_DIR}/SKILL.md"

# 3) PATH hint.
if ! command -v debate-review >/dev/null 2>&1; then
  if [ "${installed}" = "pip" ]; then
    HINT="$(python3 -m site --user-base)/bin"
  else
    HINT="${BIN_DIR}"
  fi
  echo ""
  echo "⚠ 'debate-review' not on PATH yet. Add to your shell rc:"
  echo "    export PATH=\"${HINT}:\${PATH}\""
fi

echo ""
echo "Done. Try:  cd <any-repo> && debate-review --list-skills"
