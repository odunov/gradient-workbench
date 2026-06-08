import unittest
import sys
from pathlib import Path

try:
    from gradient_workbench.core import (
        AtlasBand,
        GradientStop,
        ORIENTATION_HORIZONTAL,
        ORIENTATION_VERTICAL,
        band_uv_bounds,
        encode_color_to_srgb,
        encode_pixels_to_srgb,
        fit_bounds,
        render_atlas,
        remap_value,
        sample_stops,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core import (
        AtlasBand,
        GradientStop,
        ORIENTATION_HORIZONTAL,
        ORIENTATION_VERTICAL,
        band_uv_bounds,
        encode_color_to_srgb,
        encode_pixels_to_srgb,
        fit_bounds,
        render_atlas,
        remap_value,
        sample_stops,
    )


class GradientCoreTests(unittest.TestCase):
    def test_sample_stops_interpolates_between_neighbors(self):
        color = sample_stops(
            (
                GradientStop(0.0, (0.0, 0.0, 0.0, 1.0)),
                GradientStop(1.0, (1.0, 1.0, 1.0, 1.0)),
            ),
            0.25,
        )
        self.assertEqual(color, (0.25, 0.25, 0.25, 1.0))

    def test_band_uv_bounds_vertical_columns(self):
        bounds = band_uv_bounds(
            band_index=1,
            band_count=4,
            orientation=ORIENTATION_VERTICAL,
            width=64,
            height=64,
            padding_pixels=2,
        )
        self.assertAlmostEqual(bounds[0], 0.2890625)
        self.assertAlmostEqual(bounds[1], 0.4609375)
        self.assertAlmostEqual(bounds[2], 0.0390625)
        self.assertAlmostEqual(bounds[3], 0.9609375)

    def test_band_uv_bounds_vertical_columns_edge_mode_is_not_inset(self):
        bounds = band_uv_bounds(
            band_index=1,
            band_count=4,
            orientation=ORIENTATION_VERTICAL,
            width=64,
            height=64,
            padding_pixels=2,
            mode="EDGE",
        )
        self.assertAlmostEqual(bounds[0], 0.28125)
        self.assertAlmostEqual(bounds[1], 0.46875)
        self.assertAlmostEqual(bounds[2], 0.03125)
        self.assertAlmostEqual(bounds[3], 0.96875)

    def test_band_uv_bounds_horizontal_rows(self):
        bounds = band_uv_bounds(
            band_index=2,
            band_count=4,
            orientation=ORIENTATION_HORIZONTAL,
            width=64,
            height=64,
            padding_pixels=2,
        )
        self.assertAlmostEqual(bounds[0], 0.0390625)
        self.assertAlmostEqual(bounds[1], 0.9609375)
        self.assertAlmostEqual(bounds[2], 0.5390625)
        self.assertAlmostEqual(bounds[3], 0.7109375)

    def test_band_uv_bounds_three_columns_match_rendered_pixels(self):
        bounds = band_uv_bounds(
            band_index=2,
            band_count=3,
            orientation=ORIENTATION_VERTICAL,
            width=64,
            height=64,
            padding_pixels=0,
        )
        self.assertAlmostEqual(bounds[0], 0.6796875)
        self.assertAlmostEqual(bounds[1], 0.9921875)
        self.assertAlmostEqual(bounds[2], 0.0078125)
        self.assertAlmostEqual(bounds[3], 0.9921875)

    def test_band_uv_bounds_three_columns_edge_mode_matches_band_edges(self):
        bounds = band_uv_bounds(
            band_index=2,
            band_count=3,
            orientation=ORIENTATION_VERTICAL,
            width=64,
            height=64,
            padding_pixels=0,
            mode="EDGE",
        )
        self.assertAlmostEqual(bounds[0], 43 / 64)
        self.assertAlmostEqual(bounds[1], 64 / 64)
        self.assertAlmostEqual(bounds[2], 0.0)
        self.assertAlmostEqual(bounds[3], 1.0)

    def test_band_uv_bounds_three_columns_with_filter_gutter_only_insets_band_axis(self):
        bounds = band_uv_bounds(
            band_index=2,
            band_count=3,
            orientation=ORIENTATION_VERTICAL,
            width=64,
            height=64,
            padding_pixels=0,
            gutter_pixels=1,
            mode="EDGE",
        )
        self.assertAlmostEqual(bounds[0], 44 / 64)
        self.assertAlmostEqual(bounds[1], 63 / 64)
        self.assertAlmostEqual(bounds[2], 0.0)
        self.assertAlmostEqual(bounds[3], 1.0)

    def test_band_uv_bounds_horizontal_filter_gutter_only_insets_row_axis(self):
        bounds = band_uv_bounds(
            band_index=1,
            band_count=4,
            orientation=ORIENTATION_HORIZONTAL,
            width=64,
            height=64,
            padding_pixels=0,
            gutter_pixels=1,
            mode="EDGE",
        )
        self.assertAlmostEqual(bounds[0], 0.0)
        self.assertAlmostEqual(bounds[1], 1.0)
        self.assertAlmostEqual(bounds[2], 17 / 64)
        self.assertAlmostEqual(bounds[3], 31 / 64)

    def test_render_atlas_vertical_writes_each_column_band(self):
        atlas = render_atlas(
            [
                AtlasBand(
                    "Dark",
                    (
                        GradientStop(0.0, (0.0, 0.0, 0.0, 1.0)),
                        GradientStop(1.0, (0.0, 0.0, 0.0, 1.0)),
                    ),
                ),
                AtlasBand(
                    "Bright",
                    (
                        GradientStop(0.0, (1.0, 1.0, 1.0, 1.0)),
                        GradientStop(1.0, (1.0, 1.0, 1.0, 1.0)),
                    ),
                ),
            ],
            width=4,
            height=2,
            orientation=ORIENTATION_VERTICAL,
        )
        left_pixel = tuple(atlas[0:4])
        right_pixel = tuple(atlas[8:12])
        self.assertEqual(left_pixel, (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(right_pixel, (1.0, 1.0, 1.0, 1.0))

    def test_render_atlas_vertical_padding_preserves_gradient_endpoints(self):
        atlas = render_atlas(
            [
                AtlasBand(
                    "Padded",
                    (
                        GradientStop(0.0, (0.0, 0.0, 0.0, 1.0)),
                        GradientStop(1.0, (1.0, 1.0, 1.0, 1.0)),
                    ),
                ),
            ],
            width=3,
            height=5,
            orientation=ORIENTATION_VERTICAL,
            padding_pixels=1,
        )

        top_offset = (1 * 3 + 1) * 4
        middle_offset = (2 * 3 + 1) * 4
        bottom_offset = (3 * 3 + 1) * 4
        self.assertEqual(tuple(atlas[top_offset:top_offset + 4]), (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(tuple(atlas[middle_offset:middle_offset + 4]), (0.5, 0.5, 0.5, 1.0))
        self.assertEqual(tuple(atlas[bottom_offset:bottom_offset + 4]), (1.0, 1.0, 1.0, 1.0))

    def test_render_atlas_horizontal_padding_preserves_gradient_endpoints(self):
        atlas = render_atlas(
            [
                AtlasBand(
                    "Padded",
                    (
                        GradientStop(0.0, (0.0, 0.0, 0.0, 1.0)),
                        GradientStop(1.0, (1.0, 1.0, 1.0, 1.0)),
                    ),
                ),
            ],
            width=5,
            height=3,
            orientation=ORIENTATION_HORIZONTAL,
            padding_pixels=1,
        )

        left_offset = (1 * 5 + 1) * 4
        middle_offset = (1 * 5 + 2) * 4
        right_offset = (1 * 5 + 3) * 4
        self.assertEqual(tuple(atlas[left_offset:left_offset + 4]), (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(tuple(atlas[middle_offset:middle_offset + 4]), (0.5, 0.5, 0.5, 1.0))
        self.assertEqual(tuple(atlas[right_offset:right_offset + 4]), (1.0, 1.0, 1.0, 1.0))

    def test_encode_color_to_srgb_preserves_alpha(self):
        color = encode_color_to_srgb((0.5, 0.21404114, 0.0, 0.25))
        self.assertAlmostEqual(color[0], 0.73535698)
        self.assertAlmostEqual(color[1], 0.5)
        self.assertEqual(color[2], 0.0)
        self.assertEqual(color[3], 0.25)

    def test_encode_pixels_to_srgb_encodes_each_pixel(self):
        pixels = encode_pixels_to_srgb(
            [
                0.5, 0.21404114, 0.0, 1.0,
                1.0, 0.0, 0.5, 0.5,
            ]
        )
        self.assertAlmostEqual(pixels[0], 0.73535698)
        self.assertAlmostEqual(pixels[1], 0.5)
        self.assertEqual(pixels[2], 0.0)
        self.assertEqual(pixels[3], 1.0)
        self.assertEqual(pixels[4], 1.0)
        self.assertEqual(pixels[5], 0.0)
        self.assertAlmostEqual(pixels[6], 0.73535698)
        self.assertEqual(pixels[7], 0.5)

    def test_remap_value_handles_flat_source(self):
        value = remap_value(0.5, 1.0, 1.0, 0.2, 0.8)
        self.assertEqual(value, 0.5)

    def test_fit_bounds_preserves_aspect_by_default(self):
        bounds = fit_bounds(
            source_min_u=0.0,
            source_max_u=2.0,
            source_min_v=0.0,
            source_max_v=1.0,
            target_min_u=0.0,
            target_max_u=1.0,
            target_min_v=0.0,
            target_max_v=1.0,
        )
        self.assertEqual(bounds, (0.0, 1.0, 0.25, 0.75))

    def test_fit_bounds_can_fill_target_when_aspect_is_not_preserved(self):
        bounds = fit_bounds(
            source_min_u=0.0,
            source_max_u=2.0,
            source_min_v=0.0,
            source_max_v=1.0,
            target_min_u=0.0,
            target_max_u=1.0,
            target_min_v=0.0,
            target_max_v=1.0,
            preserve_aspect=False,
        )
        self.assertEqual(bounds, (0.0, 1.0, 0.0, 1.0))


if __name__ == "__main__":
    unittest.main()
