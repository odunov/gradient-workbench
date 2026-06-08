from __future__ import annotations

import importlib

bl_info = {
    "name": "Gradient Workbench",
    "author": "odunov",
    "version": (0, 1, 7),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Gradient WB",
    "description": "Non-destructive gradient atlas authoring and UV helpers for gradient texturing workflows.",
    "category": "Material",
}

from . import core as _core  # noqa: E402

_core = importlib.reload(_core)

AtlasBand = _core.AtlasBand
GradientStop = _core.GradientStop
ORIENTATION_HORIZONTAL = _core.ORIENTATION_HORIZONTAL
ORIENTATION_VERTICAL = _core.ORIENTATION_VERTICAL
band_uv_bounds = _core.band_uv_bounds
encode_pixels_to_srgb = _core.encode_pixels_to_srgb
fit_bounds = _core.fit_bounds
render_atlas = _core.render_atlas
remap_value = _core.remap_value

ATLAS_COLOR_MODE_SRGB = "COLOR_SRGB"
ATLAS_COLOR_MODE_LINEAR = "LINEAR_DATA"

try:
    import bmesh
    import bpy
    from bpy.props import (
        BoolProperty,
        CollectionProperty,
        EnumProperty,
        FloatProperty,
        FloatVectorProperty,
        IntProperty,
        PointerProperty,
        StringProperty,
    )
    from bpy.types import Operator, Panel, PropertyGroup
except ImportError:
    bpy = None


if bpy is not None:
    def _managed_material_name(obj_name: str) -> str:
        return f"GTB_{obj_name}"


    def _active_band_index(settings) -> int:
        if not settings.bands:
            return 0
        return max(0, min(settings.active_band_index, len(settings.bands) - 1))


    def _active_band(settings):
        if not settings.bands:
            return None
        return settings.bands[_active_band_index(settings)]


    def _replace_band_stops(band, stops_data):
        band.stops.clear()
        for position, color in stops_data:
            stop = band.stops.add()
            stop.position = position
            stop.color = color


    def _default_stops():
        return (
            (0.0, (0.16, 0.16, 0.2, 1.0)),
            (0.55, (0.55, 0.56, 0.6, 1.0)),
            (1.0, (0.93, 0.94, 1.0, 1.0)),
        )


    def _build_band_models(settings):
        bands = []
        for band in settings.bands:
            stops = tuple(
                GradientStop(position=stop.position, color=tuple(stop.color)) for stop in band.stops
            )
            bands.append(AtlasBand(name=band.name, stops=stops))
        return bands


    def _ensure_image(settings):
        image = bpy.data.images.get(settings.image_name)
        if image is None:
            image = bpy.data.images.new(
                name=settings.image_name,
                width=settings.image_width,
                height=settings.image_height,
                alpha=True,
            )
        elif image.size[0] != settings.image_width or image.size[1] != settings.image_height:
            image.scale(settings.image_width, settings.image_height)

        if settings.atlas_color_mode == ATLAS_COLOR_MODE_SRGB:
            color_space_names = ("sRGB", "Utility - sRGB - Texture", "srgb_texture")
        else:
            color_space_names = ("Working Space", "Linear Rec.709", "Linear")

        for color_space_name in color_space_names:
            try:
                image.colorspace_settings.name = color_space_name
                break
            except Exception:
                continue

        image.alpha_mode = "STRAIGHT"
        image.use_fake_user = True
        return image


    def _generate_into_image(settings):
        if not settings.bands:
            raise RuntimeError("Add at least one gradient band first.")

        image = _ensure_image(settings)
        atlas_pixels = render_atlas(
            _build_band_models(settings),
            width=settings.image_width,
            height=settings.image_height,
            orientation=settings.orientation,
            padding_pixels=settings.padding_pixels,
        )
        if settings.atlas_color_mode == ATLAS_COLOR_MODE_SRGB:
            atlas_pixels = encode_pixels_to_srgb(atlas_pixels)
        image.pixels = atlas_pixels
        image.update()
        return image


    def _mesh_uv_selected_loop_indices(context):
        obj = context.object
        if obj is None or obj.type != "MESH":
            return set()

        try:
            obj.update_from_editmode()
        except Exception:
            return set()

        uv_map = obj.data.uv_layers.active
        if uv_map is None:
            return set()

        selected = set()

        vertex_selection = getattr(uv_map, "vertex_selection", None)
        if vertex_selection is not None:
            selected = {
                index for index, item in enumerate(vertex_selection) if getattr(item, "value", False)
            }
            if selected:
                return selected

        edge_selection = getattr(uv_map, "edge_selection", None)
        if edge_selection is not None:
            selected = {
                index for index, item in enumerate(edge_selection) if getattr(item, "value", False)
            }
            if selected:
                return selected

        data = getattr(uv_map, "data", None)
        if data is not None:
            selected = {
                index for index, item in enumerate(data) if getattr(item, "select", False)
            }

        return selected


    def _selected_uv_loops(context, bm, uv_layer):
        sample_uv = None
        for face in bm.faces:
            if face.loops:
                sample_uv = face.loops[0][uv_layer]
                break

        if sample_uv is not None and hasattr(sample_uv, "select"):
            selected = [
                loop
                for face in bm.faces
                for loop in face.loops
                if getattr(loop[uv_layer], "select", False)
            ]
            if selected:
                return selected

        mesh_uv_selected = _mesh_uv_selected_loop_indices(context)
        if mesh_uv_selected:
            selected = [
                loop
                for face in bm.faces
                for loop in face.loops
                if loop.index in mesh_uv_selected
            ]
            if selected:
                return selected

        selected = [loop for face in bm.faces if face.select for loop in face.loops]
        if selected:
            return selected

        return []


    def _face_edge_uvs(face, edge, uv_layer):
        edge_vert_indices = {vert.index for vert in edge.verts}
        mapping = {}
        for loop in face.loops:
            if loop.vert.index in edge_vert_indices:
                uv = loop[uv_layer].uv
                mapping[loop.vert.index] = (round(uv.x, 6), round(uv.y, 6))
        if len(mapping) != 2:
            return None
        return mapping


    def _faces_share_uv_edge(face_a, face_b, edge, uv_layer):
        edge_uvs_a = _face_edge_uvs(face_a, edge, uv_layer)
        edge_uvs_b = _face_edge_uvs(face_b, edge, uv_layer)
        return edge_uvs_a is not None and edge_uvs_a == edge_uvs_b


    def _group_selected_loops(selected_loops, should_link_faces):
        selected_loop_set = set(selected_loops)
        selected_faces = {loop.face for loop in selected_loop_set}
        remaining_faces = set(selected_faces)
        islands = []

        while remaining_faces:
            seed_face = remaining_faces.pop()
            island_faces = {seed_face}
            stack = [seed_face]

            while stack:
                face = stack.pop()
                for edge in face.edges:
                    for linked_face in edge.link_faces:
                        if linked_face not in remaining_faces:
                            continue
                        if should_link_faces(face, linked_face, edge):
                            remaining_faces.remove(linked_face)
                            island_faces.add(linked_face)
                            stack.append(linked_face)

            island_loops = [
                loop
                for face in island_faces
                for loop in face.loops
                if loop in selected_loop_set
            ]
            if island_loops:
                islands.append(island_loops)

        return islands


    def _selected_uv_islands(context, bm, uv_layer):
        selected_loops = _selected_uv_loops(context, bm, uv_layer)
        if not selected_loops:
            return []

        return _group_selected_loops(
            selected_loops,
            lambda face, linked_face, edge: _faces_share_uv_edge(face, linked_face, edge, uv_layer),
        )


    def _selected_seam_islands(context, bm, uv_layer):
        selected_loops = _selected_uv_loops(context, bm, uv_layer)
        if not selected_loops:
            return []

        return _group_selected_loops(
            selected_loops,
            lambda face, linked_face, edge: not edge.seam,
        )


    def _operation_groups(islands, process_whole_selection):
        if not islands:
            return []
        if process_whole_selection:
            return [[loop for island in islands for loop in island]]
        return islands


    def _uv_bounds(loops, uv_layer):
        us = [loop[uv_layer].uv.x for loop in loops]
        vs = [loop[uv_layer].uv.y for loop in loops]
        return min(us), max(us), min(vs), max(vs)


    def _project_uvs_from_axis(loops, uv_layer, projection_axis):
        for loop in loops:
            co = loop.vert.co
            if projection_axis == "TOP":
                data_u, data_v = co.x, co.y
            elif projection_axis == "SIDE":
                data_u, data_v = co.y, co.z
            else:
                data_u, data_v = co.x, co.z
            data = loop[uv_layer]
            data.uv.x = data_u
            data.uv.y = data_v


    def _rotate_uvs(loops, uv_layer, rotation_mode):
        if rotation_mode == "NONE":
            return

        min_u, max_u, min_v, max_v = _uv_bounds(loops, uv_layer)
        center_u = (min_u + max_u) * 0.5
        center_v = (min_v + max_v) * 0.5

        for loop in loops:
            data = loop[uv_layer]
            rel_u = data.uv.x - center_u
            rel_v = data.uv.y - center_v
            if rotation_mode == "CW_90":
                new_u = rel_v
                new_v = -rel_u
            elif rotation_mode == "CCW_90":
                new_u = -rel_v
                new_v = rel_u
            else:
                new_u = -rel_u
                new_v = -rel_v
            data.uv.x = center_u + new_u
            data.uv.y = center_v + new_v


    def _fit_loops_to_bounds(
        loops,
        uv_layer,
        target_min_u,
        target_max_u,
        target_min_v,
        target_max_v,
        preserve_aspect,
    ):
        source_u_min, source_u_max, source_v_min, source_v_max = _uv_bounds(loops, uv_layer)
        fitted_min_u, fitted_max_u, fitted_min_v, fitted_max_v = fit_bounds(
            source_min_u=source_u_min,
            source_max_u=source_u_max,
            source_min_v=source_v_min,
            source_max_v=source_v_max,
            target_min_u=target_min_u,
            target_max_u=target_max_u,
            target_min_v=target_min_v,
            target_max_v=target_max_v,
            preserve_aspect=preserve_aspect,
        )

        for loop in loops:
            data = loop[uv_layer]
            data.uv.x = remap_value(data.uv.x, source_u_min, source_u_max, fitted_min_u, fitted_max_u)
            data.uv.y = remap_value(data.uv.y, source_v_min, source_v_max, fitted_min_v, fitted_max_v)


    def _get_mesh_edit_context(context):
        obj = context.object
        if obj is None or obj.type != "MESH":
            raise RuntimeError("Select a mesh object.")
        if obj.mode != "EDIT":
            raise RuntimeError("Switch the mesh to Edit Mode for UV tools.")

        bm = bmesh.from_edit_mesh(obj.data)
        uv_layer = bm.loops.layers.uv.verify()
        islands = _selected_uv_islands(context, bm, uv_layer)
        if not islands:
            raise RuntimeError(
                "Select some UVs or mesh elements first. "
                "If UV-only selection is not detected, enable UV Sync Selection or select the faces in the mesh."
            )
        return obj, bm, uv_layer, islands


    def _fit_margin_pixels(settings) -> int:
        if settings.texture_interpolation == "Closest":
            return 0
        if settings.texture_interpolation == "Cubic":
            return 2
        return 1


    def _active_band_bounds(settings, mode="CENTER", apply_fit_margin=False):
        if not settings.bands:
            raise RuntimeError("Add a gradient band first.")
        band_index = _active_band_index(settings)
        kwargs = dict(
            band_index=band_index,
            band_count=len(settings.bands),
            orientation=settings.orientation,
            width=settings.image_width,
            height=settings.image_height,
            padding_pixels=settings.padding_pixels,
            gutter_pixels=_fit_margin_pixels(settings) if apply_fit_margin else 0,
        )
        try:
            return band_uv_bounds(mode=mode, **kwargs)
        except TypeError:
            kwargs.pop("gutter_pixels", None)
            try:
                return band_uv_bounds(mode=mode, **kwargs)
            except TypeError:
                return band_uv_bounds(**kwargs)


    def _setup_managed_material(obj, image, settings):
        material_name = settings.material_name.strip() or _managed_material_name(obj.name)
        existing = bpy.data.materials.get(material_name)
        if existing and not existing.get("gtb_managed"):
            fallback_name = _managed_material_name(obj.name)
            fallback = bpy.data.materials.get(fallback_name)
            material_name = fallback_name
            existing = fallback if fallback and fallback.get("gtb_managed") else None

        material = existing or bpy.data.materials.new(material_name)
        material.use_nodes = True
        material["gtb_managed"] = True

        nodes = material.node_tree.nodes
        links = material.node_tree.links
        nodes.clear()

        output = nodes.new("ShaderNodeOutputMaterial")
        output.location = (340, 0)
        image_node = nodes.new("ShaderNodeTexImage")
        image_node.location = (-160, 0)
        image_node.image = image
        image_node.interpolation = settings.texture_interpolation
        image_node.extension = "EXTEND"

        if settings.shading_mode == "UNLIT":
            shader = nodes.new("ShaderNodeEmission")
            shader.location = (120, 0)
            links.new(image_node.outputs["Color"], shader.inputs["Color"])
            links.new(shader.outputs["Emission"], output.inputs["Surface"])
        else:
            shader = nodes.new("ShaderNodeBsdfPrincipled")
            shader.location = (120, 0)
            links.new(image_node.outputs["Color"], shader.inputs["Base Color"])
            links.new(shader.outputs["BSDF"], output.inputs["Surface"])

        if not obj.data.materials:
            obj.data.materials.append(material)
            obj.active_material_index = 0
        else:
            active_index = max(0, min(obj.active_material_index, len(obj.data.materials) - 1))
            active_material = obj.data.materials[active_index]
            if active_material is None or active_material.get("gtb_managed"):
                obj.data.materials[active_index] = material
            else:
                obj.data.materials.append(material)
                obj.active_material_index = len(obj.data.materials) - 1

        settings.material_name = material.name
        return material


    class GTB_GradientStop(PropertyGroup):
        position: FloatProperty(
            name="Position",
            description="0 is the dark/bottom end, 1 is the bright/top end",
            min=0.0,
            max=1.0,
            default=0.5,
        )
        color: FloatVectorProperty(
            name="Color",
            description="RGBA color at this point in the gradient",
            subtype="COLOR",
            size=4,
            min=0.0,
            max=1.0,
            default=(0.5, 0.5, 0.5, 1.0),
        )


    class GTB_GradientBand(PropertyGroup):
        name: StringProperty(name="Name", default="Band")
        stops: CollectionProperty(type=GTB_GradientStop)


    class GTB_Settings(PropertyGroup):
        image_name: StringProperty(name="Image", default="GradientAtlas")
        image_width: IntProperty(name="Width", default=64, min=1, soft_max=512)
        image_height: IntProperty(name="Height", default=64, min=1, soft_max=512)
        padding_pixels: IntProperty(name="Padding", default=0, min=0, soft_max=8)
        atlas_color_mode: EnumProperty(
            name="Atlas Type",
            items=[
                (
                    ATLAS_COLOR_MODE_SRGB,
                    "Color Map",
                    "Encode the atlas as an sRGB color texture for Blender materials and engine export",
                ),
                (
                    ATLAS_COLOR_MODE_LINEAR,
                    "Linear/Data",
                    "Keep raw linear values for special lookup or data-texture workflows",
                ),
            ],
            default=ATLAS_COLOR_MODE_SRGB,
        )
        active_band_index: IntProperty(name="Active Band", default=0, min=0)
        material_name: StringProperty(name="Material", default="")
        orientation: EnumProperty(
            name="Layout",
            items=[
                (ORIENTATION_VERTICAL, "Vertical Columns", "Bands are columns with bright at the top"),
                (ORIENTATION_HORIZONTAL, "Horizontal Rows", "Bands are rows with bright toward the right"),
            ],
            default=ORIENTATION_VERTICAL,
        )
        shading_mode: EnumProperty(
            name="Shading",
            items=[
                ("UNLIT", "Unlit", "Use an emission-only preview material"),
                ("PRINCIPLED", "Principled", "Plug the atlas into Principled Base Color"),
            ],
            default="UNLIT",
        )
        texture_interpolation: EnumProperty(
            name="Sampling",
            items=[
                ("Linear", "Linear", "Smooth sampling with a guard gutter on band edges"),
                ("Closest", "Closest", "Pixel-perfect nearest sampling"),
                ("Cubic", "Cubic", "Smoother filtering that benefits from guard gutters"),
                ("Smart", "Smart", "Blender smart filtering"),
            ],
            default="Linear",
        )
        preserve_aspect_fit: BoolProperty(
            name="Preserve Aspect",
            description="Scale uniformly to fit inside the active band instead of stretching to fill it",
            default=True,
        )
        whole_selection_reproject: BoolProperty(
            name="Whole Selection",
            description="Project and fit all selected faces as one group; when disabled, seams split the selection into islands",
            default=False,
        )
        projection_axis: EnumProperty(
            name="Project From",
            items=[
                ("FRONT", "Front", "Project from local front view using X/Z"),
                ("SIDE", "Side", "Project from local side view using Y/Z"),
                ("TOP", "Top", "Project from local top view using X/Y"),
            ],
            default="FRONT",
        )
        nudge_amount: FloatProperty(
            name="Nudge",
            description="How far to move selected UVs toward the bright or dark end",
            default=0.04,
            min=0.001,
            max=0.5,
            subtype="FACTOR",
        )
        bands: CollectionProperty(type=GTB_GradientBand)


    class GTB_OT_add_band(Operator):
        bl_idname = "gtb.add_band"
        bl_label = "Add Band"
        bl_options = {"REGISTER", "UNDO"}

        def execute(self, context):
            settings = context.scene.gtb_settings
            band = settings.bands.add()
            band.name = f"Band {len(settings.bands)}"
            _replace_band_stops(band, _default_stops())
            settings.active_band_index = len(settings.bands) - 1
            return {"FINISHED"}


    class GTB_OT_remove_band(Operator):
        bl_idname = "gtb.remove_band"
        bl_label = "Remove Band"
        bl_options = {"REGISTER", "UNDO"}

        index: IntProperty()

        def execute(self, context):
            settings = context.scene.gtb_settings
            if not settings.bands:
                return {"CANCELLED"}
            remove_index = max(0, min(self.index, len(settings.bands) - 1))
            settings.bands.remove(remove_index)
            settings.active_band_index = max(0, min(settings.active_band_index, len(settings.bands) - 1))
            return {"FINISHED"}


    class GTB_OT_set_active_band(Operator):
        bl_idname = "gtb.set_active_band"
        bl_label = "Select Band"

        index: IntProperty()

        def execute(self, context):
            settings = context.scene.gtb_settings
            settings.active_band_index = max(0, min(self.index, len(settings.bands) - 1))
            return {"FINISHED"}


    class GTB_OT_add_stop(Operator):
        bl_idname = "gtb.add_stop"
        bl_label = "Add Stop"
        bl_options = {"REGISTER", "UNDO"}

        def execute(self, context):
            settings = context.scene.gtb_settings
            band = _active_band(settings)
            if band is None:
                self.report({"ERROR"}, "Add a band first.")
                return {"CANCELLED"}
            stop = band.stops.add()
            stop.position = 0.5
            stop.color = (0.75, 0.75, 0.8, 1.0)
            return {"FINISHED"}


    class GTB_OT_remove_stop(Operator):
        bl_idname = "gtb.remove_stop"
        bl_label = "Remove Stop"
        bl_options = {"REGISTER", "UNDO"}

        index: IntProperty()

        def execute(self, context):
            settings = context.scene.gtb_settings
            band = _active_band(settings)
            if band is None:
                self.report({"ERROR"}, "Add a band first.")
                return {"CANCELLED"}
            if len(band.stops) <= 2:
                self.report({"ERROR"}, "Keep at least two stops in each band.")
                return {"CANCELLED"}
            band.stops.remove(max(0, min(self.index, len(band.stops) - 1)))
            return {"FINISHED"}


    class GTB_OT_sort_stops(Operator):
        bl_idname = "gtb.sort_stops"
        bl_label = "Sort Stops"
        bl_options = {"REGISTER", "UNDO"}

        def execute(self, context):
            settings = context.scene.gtb_settings
            band = _active_band(settings)
            if band is None:
                self.report({"ERROR"}, "Add a band first.")
                return {"CANCELLED"}
            ordered = sorted(((stop.position, tuple(stop.color)) for stop in band.stops), key=lambda item: item[0])
            _replace_band_stops(band, ordered)
            return {"FINISHED"}


    class GTB_OT_generate_atlas(Operator):
        bl_idname = "gtb.generate_atlas"
        bl_label = "Generate Atlas"
        bl_options = {"REGISTER", "UNDO"}

        def execute(self, context):
            settings = context.scene.gtb_settings
            try:
                image = _generate_into_image(settings)
            except RuntimeError as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            self.report({"INFO"}, f"Updated {image.name}")
            return {"FINISHED"}


    class GTB_OT_setup_material(Operator):
        bl_idname = "gtb.setup_material"
        bl_label = "Setup Material"
        bl_options = {"REGISTER", "UNDO"}

        def execute(self, context):
            obj = context.object
            if obj is None or obj.type != "MESH":
                self.report({"ERROR"}, "Select a mesh object.")
                return {"CANCELLED"}
            settings = context.scene.gtb_settings
            try:
                image = _generate_into_image(settings)
            except RuntimeError as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            material = _setup_managed_material(obj, image, settings)
            self.report({"INFO"}, f"Assigned {material.name}")
            return {"FINISHED"}


    class GTB_OT_fit_selected_uvs(Operator):
        bl_idname = "gtb.fit_selected_uvs"
        bl_label = "Project, Rotate, And Fit UVs"
        bl_options = {"REGISTER", "UNDO"}

        reproject: BoolProperty(
            name="Reproject",
            description="Rebuild UVs from the chosen projection axis before rotating and fitting",
            default=False,
        )
        rotation_mode: EnumProperty(
            name="Rotation",
            items=[
                ("NONE", "0", "Use the projected view as-is"),
                ("CW_90", "90 CW", "Rotate the projected UVs 90 degrees clockwise"),
                ("CCW_90", "90 CCW", "Rotate the projected UVs 90 degrees counter-clockwise"),
                ("ROT_180", "180", "Rotate the projected UVs 180 degrees"),
            ],
            default="NONE",
        )

        def execute(self, context):
            settings = context.scene.gtb_settings
            try:
                _, bm, uv_layer, islands = _get_mesh_edit_context(context)
                min_u, max_u, min_v, max_v = _active_band_bounds(
                    settings,
                    mode="EDGE",
                    apply_fit_margin=True,
                )
            except RuntimeError as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}

            if self.reproject:
                if settings.whole_selection_reproject:
                    groups = _operation_groups(islands, True)
                else:
                    groups = _selected_seam_islands(context, bm, uv_layer)
            else:
                groups = islands

            for loops in groups:
                if self.reproject:
                    _project_uvs_from_axis(loops, uv_layer, settings.projection_axis)
                _rotate_uvs(loops, uv_layer, self.rotation_mode)
                _fit_loops_to_bounds(
                    loops,
                    uv_layer,
                    min_u,
                    max_u,
                    min_v,
                    max_v,
                    settings.preserve_aspect_fit,
                )

            bmesh.update_edit_mesh(context.object.data)
            return {"FINISHED"}


    class GTB_OT_nudge_uvs(Operator):
        bl_idname = "gtb.nudge_uvs"
        bl_label = "Nudge UVs"
        bl_options = {"REGISTER", "UNDO"}

        direction: IntProperty(default=1)

        def execute(self, context):
            settings = context.scene.gtb_settings
            try:
                _, bm, uv_layer, islands = _get_mesh_edit_context(context)
                min_u, max_u, min_v, max_v = _active_band_bounds(
                    settings,
                    mode="CENTER",
                    apply_fit_margin=True,
                )
            except RuntimeError as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}

            delta = settings.nudge_amount * (1 if self.direction >= 0 else -1)
            if settings.orientation == ORIENTATION_HORIZONTAL:
                for loops in islands:
                    for loop in loops:
                        data = loop[uv_layer]
                        data.uv.x = min(max_u, max(min_u, data.uv.x + delta))
            else:
                for loops in islands:
                    for loop in loops:
                        data = loop[uv_layer]
                        data.uv.y = min(max_v, max(min_v, data.uv.y + delta))

            bmesh.update_edit_mesh(context.object.data)
            return {"FINISHED"}


    class GTB_PT_panel(Panel):
        bl_label = "Gradient WB"
        bl_idname = "GTB_PT_panel"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "Gradient WB"

        def draw(self, context):
            layout = self.layout
            settings = context.scene.gtb_settings
            active_index = _active_band_index(settings)

            atlas_box = layout.box()
            atlas_box.label(text="Atlas")
            atlas_box.prop(settings, "image_name")
            row = atlas_box.row(align=True)
            row.prop(settings, "image_width")
            row.prop(settings, "image_height")
            atlas_box.prop(settings, "padding_pixels")
            atlas_box.prop(settings, "atlas_color_mode")
            atlas_box.prop(settings, "texture_interpolation")
            atlas_box.prop(settings, "orientation")
            atlas_box.prop(settings, "shading_mode")

            bands_box = layout.box()
            bands_box.label(text="Bands")
            controls = bands_box.row(align=True)
            controls.operator("gtb.add_band", icon="ADD", text="Add")
            if settings.bands:
                remove = controls.operator("gtb.remove_band", icon="REMOVE", text="Remove")
                remove.index = active_index

            if not settings.bands:
                bands_box.label(text="No bands yet. Add one to start.")
            else:
                for index, band in enumerate(settings.bands):
                    row = bands_box.row(align=True)
                    icon = "RADIOBUT_ON" if index == active_index else "RADIOBUT_OFF"
                    select = row.operator("gtb.set_active_band", text="", icon=icon, emboss=False)
                    select.index = index
                    row.prop(band, "name", text="")
                    remove = row.operator("gtb.remove_band", text="", icon="X")
                    remove.index = index

                active_band = _active_band(settings)
                if active_band is None:
                    bands_box.label(text="Select a band to edit.")
                    return
                detail = bands_box.box()
                detail.label(text=f"Active: {active_band.name}")
                tool_row = detail.row(align=True)
                tool_row.operator("gtb.add_stop", icon="ADD", text="Add Stop")
                tool_row.operator("gtb.sort_stops", icon="SORT_ASC", text="Sort")

                for index, stop in enumerate(active_band.stops):
                    row = detail.row(align=True)
                    row.prop(stop, "position", text=f"Stop {index + 1}")
                    row.prop(stop, "color", text="")
                    remove = row.operator("gtb.remove_stop", text="", icon="X")
                    remove.index = index

            actions_box = layout.box()
            actions_box.label(text="Actions")
            actions_box.operator("gtb.generate_atlas", icon="IMAGE_DATA")
            actions_box.operator("gtb.setup_material", icon="MATERIAL")

            uv_box = layout.box()
            uv_box.label(text="UV Tools")
            uv_box.label(text="Use in Edit Mode on selected UVs/faces.")
            uv_box.prop(settings, "projection_axis")
            uv_box.prop(settings, "preserve_aspect_fit")
            uv_box.prop(settings, "whole_selection_reproject")
            fit_row = uv_box.row(align=True)
            fit_none = fit_row.operator("gtb.fit_selected_uvs", text="Project/Fit", icon="UV")
            fit_none.reproject = True
            fit_none.rotation_mode = "NONE"
            fit_cw = fit_row.operator("gtb.fit_selected_uvs", text="90 CW")
            fit_cw.reproject = False
            fit_cw.rotation_mode = "CW_90"
            fit_ccw = fit_row.operator("gtb.fit_selected_uvs", text="90 CCW")
            fit_ccw.reproject = False
            fit_ccw.rotation_mode = "CCW_90"
            fit_180 = fit_row.operator("gtb.fit_selected_uvs", text="180")
            fit_180.reproject = False
            fit_180.rotation_mode = "ROT_180"
            uv_box.prop(settings, "nudge_amount")
            nudge_row = uv_box.row(align=True)
            brighten = nudge_row.operator("gtb.nudge_uvs", text="Toward Bright")
            brighten.direction = 1
            darken = nudge_row.operator("gtb.nudge_uvs", text="Toward Dark")
            darken.direction = -1


    classes = (
        GTB_GradientStop,
        GTB_GradientBand,
        GTB_Settings,
        GTB_OT_add_band,
        GTB_OT_remove_band,
        GTB_OT_set_active_band,
        GTB_OT_add_stop,
        GTB_OT_remove_stop,
        GTB_OT_sort_stops,
        GTB_OT_generate_atlas,
        GTB_OT_setup_material,
        GTB_OT_fit_selected_uvs,
        GTB_OT_nudge_uvs,
        GTB_PT_panel,
    )


    def register():
        for cls in classes:
            bpy.utils.register_class(cls)
        bpy.types.Scene.gtb_settings = PointerProperty(type=GTB_Settings)


    def unregister():
        del bpy.types.Scene.gtb_settings
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)


else:
    def register():
        raise RuntimeError("Gradient Workbench must be registered inside Blender.")


    def unregister():
        return None
