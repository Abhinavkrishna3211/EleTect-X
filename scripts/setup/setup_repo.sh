#!/usr/bin/env bash
# EleTect X — one-shot repo setup. Run ONCE from the repo root:
#   cd EleTect-X && bash scripts/setup/setup_repo.sh
set -euo pipefail

echo "==> 1. Normalising folder structure (removing superseded folders)"
for old in cloud firmware linux ai dashboard _t docs/README_placeholder.md; do
  if [ -e "$old" ]; then rm -rf "$old" && echo "   removed $old"; fi
done

echo "==> 2. Sanity: new structure present"
for d in device/mcu device/mpu ml web/frontend web/backend web/ingest hardware/bom docs; do
  [ -d "$d" ] || { echo "   MISSING $d — aborting"; exit 1; }
done
echo "   OK"

echo "==> 3. Confirm local dev-tool config stays local (never committed)"
# Machine-local tool config and working notes are excluded via .git/info/exclude,
# which git never commits — so the tracked tree names no local tooling at all.
if [ -s .git/info/exclude ] && grep -qvE '^\s*(#|$)' .git/info/exclude; then
  echo "   local excludes configured (.git/info/exclude) — OK"
else
  echo "   WARNING: add machine-local tool config + working notes to .git/info/exclude"
fi

echo "==> 4. Git init + first commit"
if [ ! -d .git ]; then git init -q; fi
git add -A
git commit -q -m "chore: initialise EleTect X project structure" || echo "   (nothing to commit)"
git branch -M main

echo "==> 5. Create PRIVATE GitHub repo and push (requires: gh auth login done)"
if command -v gh >/dev/null 2>&1; then
  gh repo create Abhinavkrishna3211/EleTect-X --private --source=. --remote=origin --push \
    && echo "   pushed to GitHub" \
    || { echo "   gh create failed (maybe exists). Falling back to manual remote:";
         git remote get-url origin >/dev/null 2>&1 || git remote add origin https://github.com/Abhinavkrishna3211/EleTect-X.git;
         git push -u origin main; }
else
  echo "   gh not found. Run: git remote add origin https://github.com/Abhinavkrishna3211/EleTect-X.git && git push -u origin main"
fi

echo "==> 6. Create develop branch"
git checkout -b develop 2>/dev/null || git checkout develop
git push -u origin develop 2>/dev/null || true

echo "==> DONE. Next: open EleTect-X.code-workspace in VS Code and accept the recommended extensions."
