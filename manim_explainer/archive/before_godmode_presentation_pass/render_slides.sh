#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

manim-slides render scenes/rca_copilot_explainer_slides.py RCACopilotExplainerSlides

echo ""
echo "Interactive slides rendered."
echo "Run:"
echo "  cd /opt/stack/RCA_copilot/manim_explainer"
echo "  source .venv/bin/activate"
echo "  manim-slides present RCACopilotExplainerSlides"
