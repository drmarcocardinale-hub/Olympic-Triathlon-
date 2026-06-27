#!/bin/bash
# Push latest analysis script changes to GitHub.
# Run from Terminal:  bash push_update.sh
set -e

STUDY_DIR="$(cd "$(dirname "$0")" && pwd)"
PIPELINE_DIR="$HOME/Downloads/files/triathlon-study"

cd "$STUDY_DIR"
rm -f .git/index.lock .git/HEAD.lock

git config user.name  "Marco Cardinale"
git config user.email "drmarcocardinale@gmail.com"

# ── Copy updated analysis scripts from pipeline folder ────────────────────
mkdir -p src/analysis
cp "$PIPELINE_DIR/src/analysis/heat_model.py"          src/analysis/
cp "$PIPELINE_DIR/src/analysis/absolute_time_model.py" src/analysis/
echo "Analysis scripts copied"

# ── Stage files ───────────────────────────────────────────────────────────
git add triathlon_twin_artifact.html
git add setup_github.sh
git add push_update.sh
git add src/analysis/heat_model.py
git add src/analysis/absolute_time_model.py
git add src/analysis/water_temp_analysis.py
git add src/analysis/__init__.py
git add cover_letter_npj_digital_medicine.docx || true  # tracked despite .gitignore? skip if not
git status --short

# ── Commit ────────────────────────────────────────────────────────────────
git diff --cached --quiet && echo "Nothing to commit" && exit 0

git commit -m "${1:-Update analysis scripts and add water temperature analysis}"

git push origin main
echo ""
echo "Pushed to GitHub"
