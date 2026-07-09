#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x .venv/bin/manim ]]; then
  echo "Manim venv not found. Run ./scripts/setup_manim_venv.sh first." >&2
  exit 1
fi

source .venv/bin/activate

SCENE_FILE="scenes/rca_copilot_explainer.py"
SCENE_NAME="${2:-RCACopilotExplainer}"
FINAL_OUT="renders/rca_copilot_explainer_1080p.mp4"
SUMMARY_OUT="renders/rca_copilot_30s_summary_1080p.mp4"

case "${1:-preview}" in
  preview)
    manim -pql "$SCENE_FILE" "$SCENE_NAME"
    ;;
  final)
    manim -pqh "$SCENE_FILE" "$SCENE_NAME"
    mkdir -p renders
    if [[ "$SCENE_NAME" == "RCACopilotThirtySecondSummary" ]]; then
      cp "media/videos/rca_copilot_explainer/1080p60/RCACopilotThirtySecondSummary.mp4" "$SUMMARY_OUT"
      echo "Copied final video to $SUMMARY_OUT"
    else
      cp "media/videos/rca_copilot_explainer/1080p60/RCACopilotExplainer.mp4" "$FINAL_OUT"
      echo "Copied final video to $FINAL_OUT"
    fi
    ;;
  frames)
    mkdir -p renders/frames
    ffmpeg -y -i "$FINAL_OUT" -vf fps=1 renders/frames/frame_%03d.png
    ;;
  clean)
    rm -rf media renders/frames "$FINAL_OUT" "$SUMMARY_OUT"
    mkdir -p renders
    ;;
  *)
    echo "Usage: ./scripts/render.sh {preview|final|frames|clean} [SceneName]" >&2
    echo "Scenes: RCACopilotExplainer, RCACopilotThirtySecondSummary" >&2
    exit 1
    ;;
esac
