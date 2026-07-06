# OpenStack RCA Copilot Beamer Presentation

This folder contains the redesigned professional Beamer presentation for the OpenStack RCA Copilot project.

## Main Deliverables

- `openstack_rca_copilot_beamer.tex` - redesigned Beamer source.
- `openstack_rca_copilot_beamer.pdf` - compiled presentation.
- `speaker_notes.md` - slide-by-slide presenter notes.
- `archive/openstack_rca_copilot_beamer_simple.tex` - archived previous simple version.

## Supporting Folders

- `build/` - LaTeX auxiliary files, rendered slide previews, and contact sheets.
- `figures/` - reserved for future extracted figure assets.
- `sections/` - reserved for future split Beamer section files.

## Build

From `latex/`:

```sh
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=build openstack_rca_copilot_beamer.tex
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=build openstack_rca_copilot_beamer.tex
cp build/openstack_rca_copilot_beamer.pdf openstack_rca_copilot_beamer.pdf
```

`latexmk` was not available in this environment, so the deck was built with `pdflatex`.

## Visual Review

Rendered previews can be regenerated with:

```sh
rm -f build/preview-*.png build/contact_sheet*.png
pdftoppm -r 90 -png openstack_rca_copilot_beamer.pdf build/preview
montage build/preview-*.png -thumbnail 320x180 -tile 4x -geometry +8+8 build/contact_sheet_passN.png
```

The deck uses semantic colors:

- Deep navy: machine boundaries and global architecture.
- Medium blue: implemented processing services.
- Teal: transformations and enrichment.
- Muted green: completed or healthy states.
- Amber: decisions, warnings, checkpoints, and filters.
- Muted red: errors, seeds, and failure conditions.
- Purple: correlation graph logic and inference paths.
- Slate gray: storage, metadata, and background systems.
- Dotted gray: future components.
