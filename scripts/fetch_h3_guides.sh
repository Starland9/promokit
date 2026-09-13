#!/usr/bin/env bash
# Télécharge les guides de prompt officiels MiniMax H3 (non redistribués dans ce dépôt).
# Source : https://github.com/MiniMax-AI/MiniMax-H3 (skills/h3-prompt-writing), licence MiniMax H3 Community License.
set -euo pipefail
KIT="$(cd -P "$(dirname "$0")/.." && pwd)"
REF="${1:-d21241f0a4b3acbb34c97dae47fa417b7065e438}"
BASE="https://raw.githubusercontent.com/MiniMax-AI/MiniMax-H3/$REF/skills/h3-prompt-writing"
for dst in "$KIT/.claude/skills/h3-prompting" "$KIT/docs/h3-prompting"; do
  mkdir -p "$dst"
  for f in base-en.txt ref-en.txt; do curl -fsSL "$BASE/references/$f" -o "$dst/$f"; done
done
curl -fsSL "$BASE/SKILL.md" -o "$KIT/docs/h3-prompting/SKILL.md"
echo "guides H3 installés (commit $REF)"
