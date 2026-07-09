# RCA Copilot Manim Explainer

Standalone Manim project for a mentor presentation of the OpenStack RCA Copilot pipeline.

The animation explains:

`OpenStack logs -> raw journal records -> parsing -> structured events -> graph nodes -> correlation edges -> incident seed -> bounded incident subgraph -> enriched evidence package -> Horizon investigation dashboard -> future AI/RAG explanation`

It is intentionally separate from the RCA backend runtime. It does not require Docker, MongoDB, OpenStack, Horizon, or any live AI provider.

## Setup

```bash
cd /opt/stack/RCA_copilot/manim_explainer
./scripts/setup_manim_venv.sh
```

The setup script installs Ubuntu packages needed by Manim, creates a dedicated `.venv`, installs Manim Community Edition, and verifies `manim --version`.

## Render

Quick preview:

```bash
./scripts/render.sh preview
```

Final 1080p render:

```bash
./scripts/render.sh final
```

Expected output:

```text
renders/rca_copilot_explainer_1080p.mp4
```

Thirty-second summary:

```bash
./scripts/render.sh preview RCACopilotThirtySecondSummary
./scripts/render.sh final RCACopilotThirtySecondSummary
```

Expected output:

```text
renders/rca_copilot_30s_summary_1080p.mp4
```

## Interactive slide presentation

The original MP4 generator remains:

```text
scenes/rca_copilot_explainer.py
```

The interactive slide version is:

```text
scenes/rca_copilot_explainer_slides.py
```

### Install dependency

```bash
cd /opt/stack/RCA_copilot/manim_explainer
source .venv/bin/activate
pip install manim-slides
```

### Render interactive slides

```bash
bash scripts/render_slides.sh
```

### Present interactively

```bash
bash scripts/present_slides.sh
```

### Direct commands

```bash
manim-slides render scenes/rca_copilot_explainer_slides.py RCACopilotExplainerSlides
manim-slides present RCACopilotExplainerSlides
```

### Controls

```text
Space / Right Arrow = next
Left Arrow          = previous
F                   = fullscreen
Esc / Q             = quit
```

## Extract Frames

After the final render:

```bash
./scripts/render.sh frames
```

Frames are written to:

```text
renders/frames/frame_001.png
```

These PNGs can be reused in Beamer or review notes.

## Troubleshooting

- If `manim` is missing, run `./scripts/setup_manim_venv.sh`.
- If text rendering fails because LaTeX packages are unavailable, this scene mostly uses Manim `Text` and simple shapes, so installing the packages listed in the setup script is usually enough.
- If `ffmpeg` is missing, rerun setup or install `ffmpeg`.
- If final rendering is slow, use `./scripts/render.sh preview` while editing.

## Editing Duration

The main scene is split into chapter methods in `scenes/rca_copilot_explainer.py`.

- To shorten: reduce `self.wait(...)` calls and use shorter `run_time` values.
- To extend: add one focused animation per chapter rather than adding dense text.
- Keep captions short and use the helper functions for consistent style.

## Design Notes

- Edges show correlation, not proven causality.
- Future AI/RAG is shown with dashed boundaries.
- The evidence package remains the source of truth.
- No external branding or proprietary visual assets are used.
