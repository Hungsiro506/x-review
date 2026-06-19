#!/usr/bin/env bash
# One-line installer for x-review:
#   curl -fsSL https://raw.githubusercontent.com/Hungsiro506/x-review/main/get.sh | bash
#
# Clones (or updates) x-review to a stable location and runs its installer,
# which adds the `x-review` command and the /x-review Claude Code skill.
# Assumes you already have the reviewer CLIs (claude / codex) installed.
set -euo pipefail

REPO="${X_REVIEW_REPO:-https://github.com/Hungsiro506/x-review}"
DEST="${X_REVIEW_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/x-review}"

for dep in git python3; do
  command -v "$dep" >/dev/null 2>&1 || { echo "error: '$dep' is required but not found."; exit 1; }
done

if [ -d "$DEST/.git" ]; then
  echo "Updating x-review in $DEST"
  git -C "$DEST" pull --ff-only --quiet || git -C "$DEST" pull --ff-only
else
  echo "Installing x-review into $DEST"
  mkdir -p "$(dirname "$DEST")"
  git clone --depth 1 "$REPO" "$DEST" --quiet
fi

bash "$DEST/install.sh"
