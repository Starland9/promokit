#!/usr/bin/env bash
# (Re)télécharge les polices Google Fonts (SIL Open Font License) du template (utilisées aussi par examples/), avec leur licence.
set -euo pipefail
KIT="$(cd -P "$(dirname "$0")/.." && pwd)"
get() { # family_dir file dest_dir
  mkdir -p "$3"; curl -fsSL "https://github.com/google/fonts/raw/main/ofl/$1/$2" -o "$3/$(echo "$2" | sed -E 's/\[.*\]//; s/%5B.*%5D//')" ; curl -fsSL "https://raw.githubusercontent.com/google/fonts/main/ofl/$1/OFL.txt" -o "$3/OFL-$1.txt"; }
d="$KIT/templates/project/assets/fonts"
get sora "Sora%5Bwght%5D.ttf" "$d"; get dmsans "DMSans%5Bopsz%2Cwght%5D.ttf" "$d"; get inter "Inter%5Bopsz%2Cwght%5D.ttf" "$d"
echo "polices installées"
