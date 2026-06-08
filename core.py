from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

EPSILON = 1e-8
DEFAULT_COLOR = (0.5, 0.5, 0.5, 1.0)
ORIENTATION_VERTICAL = "VERTICAL_COLUMNS"
ORIENTATION_HORIZONTAL = "HORIZONTAL_ROWS"


Color = tuple[float, float, float, float]


@dataclass(frozen=True)
class GradientStop:
    position: float
    color: Color


@dataclass(frozen=True)
class AtlasBand:
    name: str
    stops: tuple[GradientStop, ...]


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def sanitize_color(color: Sequence[float]) -> Color:
    values = list(color[:4])
    if len(values) < 4:
        values.extend([1.0] * (4 - len(values)))
    return tuple(clamp(component) for component in values)  # type: ignore[return-value]


def linear_to_srgb(value: float) -> float:
    clamped = clamp(value)
    if clamped <= 0.0:
        return 0.0
    if clamped >= 1.0:
        return 1.0
    if clamped <= 0.0031308:
        return clamp(12.92 * clamped)
    return clamp(1.055 * (clamped ** (1.0 / 2.4)) - 0.055)


def encode_color_to_srgb(color: Sequence[float]) -> Color:
    linear = sanitize_color(color)
    return (
        linear_to_srgb(linear[0]),
        linear_to_srgb(linear[1]),
        linear_to_srgb(linear[2]),
        linear[3],
    )


def encode_pixels_to_srgb(pixels: Iterable[float]) -> list[float]:
    encoded: list[float] = []
    channels = list(pixels)
    for index in range(0, len(channels), 4):
        rgba = sanitize_color(channels[index:index + 4])
        encoded.extend(encode_color_to_srgb(rgba))
    return encoded


def normalize_stops(stops: Iterable[GradientStop | dict]) -> tuple[GradientStop, ...]:
    normalized: list[GradientStop] = []
    for stop in stops:
        if isinstance(stop, GradientStop):
            normalized.append(
                GradientStop(
                    position=clamp(stop.position),
                    color=sanitize_color(stop.color),
                )
            )
        else:
            normalized.append(
                GradientStop(
                    position=clamp(float(stop["position"])),
                    color=sanitize_color(stop["color"]),
                )
            )
    normalized.sort(key=lambda item: item.position)
    return tuple(normalized)


def lerp_color(color_a: Color, color_b: Color, factor: float) -> Color:
    t = clamp(factor)
    return tuple(
        color_a[index] + (color_b[index] - color_a[index]) * t for index in range(4)
    )  # type: ignore[return-value]


def sample_stops(stops: Iterable[GradientStop | dict], position: float) -> Color:
    ordered = normalize_stops(stops)
    if not ordered:
        return DEFAULT_COLOR

    t = clamp(position)
    if t <= ordered[0].position:
        return ordered[0].color
    if t >= ordered[-1].position:
        return ordered[-1].color

    for left, right in zip(ordered, ordered[1:]):
        if left.position <= t <= right.position:
            span = right.position - left.position
            if span <= EPSILON:
                return right.color
            local_t = (t - left.position) / span
            return lerp_color(left.color, right.color, local_t)

    return ordered[-1].color


def _pixel_region(size: int, start: int, end: int, mode: str = "CENTER") -> tuple[float, float]:
    clamped_size = max(1, int(size))
    clamped_start = max(0, min(clamped_size, int(start)))
    clamped_end = max(clamped_start, min(clamped_size, int(end)))

    if clamped_end <= clamped_start:
        pixel_index = min(clamped_size - 1, clamped_start)
        if mode == "EDGE":
            edge = pixel_index / clamped_size
            return edge, edge
        center = (pixel_index + 0.5) / clamped_size
        return center, center

    if mode == "EDGE":
        return clamped_start / clamped_size, clamped_end / clamped_size
    return (clamped_start + 0.5) / clamped_size, (clamped_end - 0.5) / clamped_size


def _band_pixel_range(
    band_index: int,
    band_count: int,
    size: int,
    padding_pixels: int,
) -> tuple[int, int]:
    clamped_size = max(1, int(size))
    count = max(1, int(band_count))
    padding = max(0, int(padding_pixels))
    slot_size = clamped_size / count
    start = int(round(band_index * slot_size)) + padding
    end = int(round((band_index + 1) * slot_size)) - padding
    start = max(0, min(clamped_size, start))
    end = max(start, min(clamped_size, end))
    return start, end


def _inset_pixel_range(start: int, end: int, inset_pixels: int) -> tuple[int, int]:
    inset = max(0, int(inset_pixels))
    inset_start = start + inset
    inset_end = end - inset
    if inset_end < inset_start:
        midpoint = int(round((start + end) * 0.5))
        midpoint = max(start, min(end, midpoint))
        return midpoint, midpoint
    return inset_start, inset_end


def band_uv_bounds(
    band_index: int,
    band_count: int,
    orientation: str,
    width: int,
    height: int,
    padding_pixels: int,
    gutter_pixels: int = 0,
    mode: str = "CENTER",
) -> tuple[float, float, float, float]:
    atlas_width = max(1, int(width))
    atlas_height = max(1, int(height))
    count = max(1, int(band_count))
    padding = max(0, int(padding_pixels))
    gutter = max(0, int(gutter_pixels))

    if orientation == ORIENTATION_HORIZONTAL:
        min_u, max_u = _pixel_region(atlas_width, padding, atlas_width - padding, mode=mode)
        start_v, end_v = _band_pixel_range(band_index, count, atlas_height, padding)
        start_v, end_v = _inset_pixel_range(start_v, end_v, gutter)
        min_v, max_v = _pixel_region(atlas_height, start_v, end_v, mode=mode)
    else:
        start_u, end_u = _band_pixel_range(band_index, count, atlas_width, padding)
        start_u, end_u = _inset_pixel_range(start_u, end_u, gutter)
        min_u, max_u = _pixel_region(atlas_width, start_u, end_u, mode=mode)
        min_v, max_v = _pixel_region(atlas_height, padding, atlas_height - padding, mode=mode)

    return min_u, max_u, min_v, max_v


def remap_value(
    value: float,
    source_min: float,
    source_max: float,
    target_min: float,
    target_max: float,
) -> float:
    if abs(source_max - source_min) <= EPSILON:
        return (target_min + target_max) * 0.5
    factor = (value - source_min) / (source_max - source_min)
    return target_min + factor * (target_max - target_min)


def fit_bounds(
    source_min_u: float,
    source_max_u: float,
    source_min_v: float,
    source_max_v: float,
    target_min_u: float,
    target_max_u: float,
    target_min_v: float,
    target_max_v: float,
    preserve_aspect: bool = True,
) -> tuple[float, float, float, float]:
    if not preserve_aspect:
        return target_min_u, target_max_u, target_min_v, target_max_v

    source_width = max(0.0, source_max_u - source_min_u)
    source_height = max(0.0, source_max_v - source_min_v)
    target_width = max(0.0, target_max_u - target_min_u)
    target_height = max(0.0, target_max_v - target_min_v)

    if source_width <= EPSILON and source_height <= EPSILON:
        center_u = (target_min_u + target_max_u) * 0.5
        center_v = (target_min_v + target_max_v) * 0.5
        return center_u, center_u, center_v, center_v

    scale_u = float("inf") if source_width <= EPSILON else target_width / source_width
    scale_v = float("inf") if source_height <= EPSILON else target_height / source_height
    scale = min(scale_u, scale_v)

    fitted_width = 0.0 if source_width <= EPSILON else source_width * scale
    fitted_height = 0.0 if source_height <= EPSILON else source_height * scale

    fitted_min_u = target_min_u + (target_width - fitted_width) * 0.5
    fitted_min_v = target_min_v + (target_height - fitted_height) * 0.5
    return (
        fitted_min_u,
        fitted_min_u + fitted_width,
        fitted_min_v,
        fitted_min_v + fitted_height,
    )


def flatten_pixels(pixels: Iterable[Color]) -> list[float]:
    flattened: list[float] = []
    for pixel in pixels:
        flattened.extend(pixel)
    return flattened


def _sample_position(pixel_index: int, start: int, end: int) -> float:
    if end - start <= 1:
        return 0.0
    return (pixel_index - start) / (end - start - 1)


def render_atlas(
    bands: Sequence[AtlasBand],
    width: int,
    height: int,
    orientation: str = ORIENTATION_VERTICAL,
    padding_pixels: int = 0,
    background: Color = (0.0, 0.0, 0.0, 0.0),
) -> list[float]:
    atlas_width = max(1, int(width))
    atlas_height = max(1, int(height))
    padding = max(0, int(padding_pixels))
    pixels: list[Color] = [background] * (atlas_width * atlas_height)

    if not bands:
        return flatten_pixels(pixels)

    band_count = len(bands)
    slot_width = atlas_width / band_count
    slot_height = atlas_height / band_count
    fill_start_x = max(0, min(atlas_width, padding))
    fill_end_x = max(fill_start_x, min(atlas_width, atlas_width - padding))
    fill_start_y = max(0, min(atlas_height, padding))
    fill_end_y = max(fill_start_y, min(atlas_height, atlas_height - padding))

    for band_index, band in enumerate(bands):
        ordered_stops = normalize_stops(band.stops)
        if not ordered_stops:
            continue

        if orientation == ORIENTATION_HORIZONTAL:
            start_y = int(round(band_index * slot_height)) + padding
            end_y = int(round((band_index + 1) * slot_height)) - padding
            start_y = max(0, min(atlas_height, start_y))
            end_y = max(start_y, min(atlas_height, end_y))
            for y in range(start_y, end_y):
                for x in range(fill_start_x, fill_end_x):
                    position = _sample_position(x, fill_start_x, fill_end_x)
                    pixels[y * atlas_width + x] = sample_stops(ordered_stops, position)
        else:
            start_x = int(round(band_index * slot_width)) + padding
            end_x = int(round((band_index + 1) * slot_width)) - padding
            start_x = max(0, min(atlas_width, start_x))
            end_x = max(start_x, min(atlas_width, end_x))
            for y in range(fill_start_y, fill_end_y):
                position = _sample_position(y, fill_start_y, fill_end_y)
                color = sample_stops(ordered_stops, position)
                row_offset = y * atlas_width
                for x in range(start_x, end_x):
                    pixels[row_offset + x] = color

    return flatten_pixels(pixels)
