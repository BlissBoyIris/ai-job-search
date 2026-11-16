#!/bin/zsh
# Double-click to open the Job Desk dashboard at http://127.0.0.1:3300 (Mac).
# Linux: cd dashboard && npm install && npm run build && npm run start (Windows: not supported yet)
cd "$(dirname "$0")/dashboard" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/TeX/texbin:$PATH"
if ! command -v npm >/dev/null 2>&1; then
  echo "Job Desk needs Node.js. Get it from https://nodejs.org (the LTS button), then double-click this again."
  read -r "?Press Enter to close."
  exit 1
fi
if curl -s -o /dev/null http://127.0.0.1:3300/api/jobs; then
  open http://127.0.0.1:3300
  exit 0
fi
[ -d node_modules ] || npm install
[ -d .next ] || npm run build
(sleep 4 && open http://127.0.0.1:3300) &
npm run start
