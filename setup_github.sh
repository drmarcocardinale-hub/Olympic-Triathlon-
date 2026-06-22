#!/bin/bash
# Push the Olympic Triathlon Study to a new GitHub repository.
# Run from Terminal: bash setup_github.sh <github-username> <repo-name>
# Example:          bash setup_github.sh marcocardinale olympic-triathlon-study
set -e

USERNAME="${1:?Usage: bash setup_github.sh <github-username> <repo-name>}"
REPO="${2:?Usage: bash setup_github.sh <github-username> <repo-name>}"

STUDY_DIR="$(cd "$(dirname "$0")" && pwd)"
PIPELINE_DIR="$HOME/Downloads/files/triathlon-study"

echo "📁 Repo root : $STUDY_DIR"
echo "📁 Pipeline  : $PIPELINE_DIR"
echo ""

# ── 1. Clear stale git lock ──────────────────────────────────────────────────
rm -f "$STUDY_DIR/.git/index.lock"

cd "$STUDY_DIR"
git config user.name  "Marco Cardinale"
git config user.email "drmarcocardinale@gmail.com"
git checkout -b main 2>/dev/null || git checkout main

# ── 2. Copy Python pipeline files into src/ ──────────────────────────────────
if [ -d "$PIPELINE_DIR/src" ]; then
  echo "📦 Copying pipeline source files..."
  mkdir -p src/analysis src/scrape src/twin src/wbgt
  cp "$PIPELINE_DIR/src/analysis/build_dataset.py"       src/analysis/
  cp "$PIPELINE_DIR/src/analysis/heat_model.py"          src/analysis/
  cp "$PIPELINE_DIR/src/analysis/absolute_time_model.py" src/analysis/
  cp "$PIPELINE_DIR/src/analysis/podium_model.py"        src/analysis/
  cp "$PIPELINE_DIR/src/scrape/build_manifest.py"        src/scrape/
  cp "$PIPELINE_DIR/src/scrape/scrape_results.py"        src/scrape/
  cp "$PIPELINE_DIR/src/scrape/scrape_results_fallback.py" src/scrape/
  cp "$PIPELINE_DIR/src/scrape/scrape_rankings.py"       src/scrape/
  cp "$PIPELINE_DIR/src/twin/twin.py"                    src/twin/
  cp "$PIPELINE_DIR/src/wbgt/wbgt.py"                   src/wbgt/
  touch src/analysis/__init__.py src/scrape/__init__.py src/twin/__init__.py src/wbgt/__init__.py
  echo "   ✅ src/ populated"
else
  echo "   ⚠️  Pipeline folder not found at $PIPELINE_DIR — skipping src/ copy."
fi

if [ -d "$PIPELINE_DIR/app" ]; then
  mkdir -p app
  cp "$PIPELINE_DIR/app/streamlit_app.py"     app/
  cp "$PIPELINE_DIR/app/requirements_app.txt" app/
  echo "   ✅ app/ populated"
fi

for f in requirements.txt config.yaml; do
  [ -f "$PIPELINE_DIR/$f" ] && cp "$PIPELINE_DIR/$f" . && echo "   ✅ $f"
done

# ── 3. Update .gitignore ─────────────────────────────────────────────────────
cat > .gitignore << 'EOF'
# Binary / Office documents
*.docx
*.pptx
*.pdf

# Figures (regeneratable)
*.png
*.jpg
*.jpeg

# Python cache
__pycache__/
*.pyc
*.pyo
*.pyd
.env

# Node
node_modules/
package-lock.json
package.json

# Data (raw scraped data not committed)
data/raw/
outputs/

# macOS
.DS_Store

# Git lock
*.lock
EOF

# ── 4. Stage coding files only ───────────────────────────────────────────────
echo ""
echo "📋 Staging files..."
git add .gitignore README.md
git add triathlon_twin_artifact.html
git add discipline_contributions.csv
[ -f requirements.txt ] && git add requirements.txt
[ -f config.yaml ]      && git add config.yaml
[ -d src ]              && git add src/
[ -d app ]              && git add app/
git status --short

# ── 5. Commit ────────────────────────────────────────────────────────────────
git commit -m "Initial commit: Olympic Triathlon Heat Study

Analysis of WBGT effects on elite triathlon run performance.
n = 3,449 athlete-races across 59 World Triathlon Series events (2009-2023).

Structure:
  triathlon_twin_artifact.html  — interactive digital twin (standalone HTML)
  src/scrape/                   — World Triathlon API scraper + rankings
  src/analysis/                 — dataset builder, heat model, podium model
  src/wbgt/                     — Liljegren (2008) physical WBGT calculator
  src/twin/                     — backend twin prediction engine
  app/                          — Streamlit web app wrapper
  discipline_contributions.csv  — OLS discipline weights by sex

Key results:
  Men   β_heat = −0.006 z/°C (p = 0.002)
  Women β_heat = 0.000 (NS)
  Water temperature: no independent swim effect after WBGT adjustment (p > 0.55)"

# ── 6. Push ──────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "👉  Now go to https://github.com/new and create:"
echo "    Repository name : $REPO"
echo "    Visibility      : Public or Private (your choice)"
echo "    ⚠️  Do NOT tick 'Add a README' or 'Add .gitignore'"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
read -rp "Press Enter once the empty repo is created..."

git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/${USERNAME}/${REPO}.git"
git push -u origin main

echo ""
echo "✅ Done! https://github.com/${USERNAME}/${REPO}"
