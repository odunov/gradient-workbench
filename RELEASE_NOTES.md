# Release Notes

## v0.1.7

Initial public release of Gradient Workbench.

- Adds procedural gradient atlas authoring inside Blender.
- Supports editable bands and color stops stored as Blender properties.
- Generates `Color Map` (`sRGB`) or `Linear/Data` atlases.
- Creates a managed preview material for selected mesh objects.
- Fits selected UVs or faces into the active gradient band.
- Supports Front, Side, and Top reprojection before fitting.
- Includes 90 degree clockwise, 90 degree counter-clockwise, and 180 degree UV rotation actions.
- Includes bright/dark UV nudge actions for gradient highlight and shadow placement.
- Includes non-Blender unit tests for atlas generation, UV bounds, fit math, and color encoding.

Validation:

- `python -m unittest discover -s tests -v`
- `python -m compileall -q .`

Blender runtime validation should still be performed manually after installing the release zip.
