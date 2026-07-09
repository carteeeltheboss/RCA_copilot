#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/5] Installing Ubuntu packages needed by Manim..."
sudo apt update
sudo apt install -y \
  python3-venv \
  python3-dev \
  build-essential \
  pkg-config \
  libcairo2-dev \
  libpango1.0-dev \
  ffmpeg \
  texlive-latex-base \
  texlive-latex-extra \
  texlive-fonts-recommended \
  dvisvgm

echo "[2/5] Creating dedicated virtual environment..."
python3 -m venv .venv

echo "[3/5] Installing Manim Community Edition..."
source .venv/bin/activate
pip install --upgrade pip wheel setuptools
pip install -r requirements.txt

echo "[4/5] Verifying Manim..."
manim --version

echo "[5/5] Ready."
echo
echo "Preview render:"
echo "  ./scripts/render.sh preview"
echo
echo "Final render:"
echo "  ./scripts/render.sh final"
echo
echo "Frame extraction after final render:"
echo "  ./scripts/render.sh frames"
