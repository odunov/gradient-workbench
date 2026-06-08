# Gradient Workbench

Gradient Workbench is a focused Blender add-on for procedural gradient atlas authoring and UV placement. It is built for gradient texturing workflows where small editable color ramps are packed into an atlas, then selected mesh UVs are projected or nudged into the active band.

## Features

- Create low-resolution gradient atlases directly inside Blender.
- Edit bands and color stops as Blender properties instead of repainting external images.
- Generate either `Color Map` (`sRGB`) atlases for material preview/export or `Linear/Data` atlases for lookup workflows.
- Build a managed preview material using the generated atlas.
- Fit selected UVs or faces into the active gradient band.
- Reproject from local Front, Side, or Top before fitting.
- Rotate fitted UVs with `90 CW`, `90 CCW`, and `180` presets.
- Nudge selected UVs toward bright or dark areas for highlight and shadow tweaks.

## Install

1. Download `gradient_workbench-v0.1.7.zip` from the GitHub release.
2. In Blender, open `Edit > Preferences > Add-ons`.
3. Click `Install...` and select the zip.
4. Enable `Gradient Workbench`.
5. Open `View3D > Sidebar > Gradient WB`.

## Suggested Workflow

1. Add bands that match your palette families.
2. Set dark-to-bright stops for each band.
3. Click `Generate Atlas`.
4. Leave `Atlas Type` on `Color Map` for Blender material preview and Unity base-color export. Use `Linear/Data` only when you intentionally need raw linear texture values.
5. Pick `Sampling`:
   - `Closest` for hard texel-accurate band edges
   - `Linear` or `Smart` for smoother sampling with automatic fit margins on band edges
   - `Cubic` for the softest result, with a slightly stronger automatic fit margin
6. Click `Setup Material` on the target mesh.
7. In Edit Mode, choose `Project From` as `Front`, `Side`, or `Top`.
8. Leave `Preserve Aspect` enabled if you want bounding-box fit without stretch.
9. Enable `Whole Selection` when you want the current selection treated as one projection/fit group.
10. Use `Project/Fit`, `90 CW`, `90 CCW`, or `180` to reproject and pack the selection into the active band.
11. Use `Toward Bright` or `Toward Dark` for quick lighting-style adjustments.

## Development

Run the non-Blender tests with:

```powershell
python -m unittest discover -s tests -v
```

The test suite covers the pure Python atlas and UV math. Blender runtime behavior should still be validated in Blender before publishing a release.

## Limitations

- Gradient Workbench is a compact UV and atlas workflow tool, not a full paint-layer replacement.
- UV fitting is selection-based and does not assign bands automatically from normals or materials.
- Blender runtime behavior is not covered by the non-Blender unit tests.

## License

Gradient Workbench is licensed under the GNU General Public License v3.0 or later. See `LICENSE`.
