from __future__ import annotations

import hashlib
import math
import random
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

from .layout_engine import GlyphPlacement


class HandwritingFontError(RuntimeError):
    pass


class HandwritingRenderer:
    DPI = 300
    INK = (29, 43, 58, 238)

    def __init__(self, font_path: Path) -> None:
        self.font_path = font_path.resolve()
        if not self.font_path.is_file():
            raise HandwritingFontError("手写字体文件缺失，请重新安装应用")

    def missing_characters(self, texts: list[str]) -> list[str]:
        missing_signatures = {
            self._glyph_signature("\u0378"),
            self._glyph_signature("\U0010ffff"),
        }
        missing: set[str] = set()
        for char in "".join(texts):
            if char.isspace():
                continue
            signature = self._glyph_signature(char)
            if signature[0] is None or signature in missing_signatures:
                missing.add(char)
        return sorted(missing)

    def render_page(
        self,
        placements: tuple[GlyphPlacement, ...],
        page_index: int,
        width_mm: float,
        height_mm: float,
        seed: int,
    ) -> Image.Image:
        width_px = round(width_mm * self.DPI / 25.4)
        height_px = round(height_mm * self.DPI / 25.4)
        page = Image.new("RGBA", (width_px, height_px), (0, 0, 0, 0))
        for placement in placements:
            if placement.page_index != page_index or placement.char.isspace():
                continue
            rng = self._random(seed, placement)
            size_pt = placement.font_size * rng.uniform(0.97, 1.03)
            size_px = max(8, round(size_pt * self.DPI / 72.0))
            mask, anchor, groups = self._glyph(placement.char, size_px)
            mask = self._perturb_components(mask, groups, rng, size_px)
            mask = mask.rotate(
                rng.uniform(-1.5, 1.5),
                resample=Image.Resampling.BICUBIC,
                center=anchor,
                expand=False,
                fillcolor=0,
            )
            x_mm = placement.x_mm + rng.uniform(-0.25, 0.25)
            baseline_mm = placement.baseline_y_mm + rng.uniform(-0.35, 0.35)
            target_x = round(x_mm * self.DPI / 25.4)
            target_baseline = round(baseline_mm * self.DPI / 25.4)
            left = target_x - anchor[0]
            top = target_baseline - anchor[1]
            ink = Image.new("RGBA", mask.size, self.INK)
            alpha = mask.point(lambda value: round(value * self.INK[3] / 255))
            ink.putalpha(alpha)
            page.alpha_composite(ink, (left, top))
        return page

    def _random(self, seed: int, placement: GlyphPlacement) -> random.Random:
        payload = (
            f"{seed}|{placement.field_key}|{placement.char_index}|{ord(placement.char)}"
        ).encode("utf-8")
        digest = hashlib.blake2b(payload, digest_size=16).digest()
        return random.Random(int.from_bytes(digest, "big"))

    @lru_cache(maxsize=1024)
    def _font(self, size_px: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(self.font_path), size_px)

    @lru_cache(maxsize=4096)
    def _glyph_signature(self, char: str) -> tuple[tuple[int, int] | None, bytes]:
        font = self._font(64)
        mask = font.getmask(char, mode="L")
        bbox = mask.getbbox()
        return (None if bbox is None else mask.size, bytes(mask))

    @lru_cache(maxsize=768)
    def _glyph(
        self, char: str, size_px: int
    ) -> tuple[Image.Image, tuple[int, int], tuple[tuple[tuple[int, int], ...], ...]]:
        font = self._font(size_px)
        probe = Image.new("L", (1, 1), 0)
        draw = ImageDraw.Draw(probe)
        bbox = draw.textbbox((0, 0), char, font=font, anchor="ls")
        padding = max(8, round(size_px * 0.45))
        width = max(1, bbox[2] - bbox[0]) + padding * 2
        height = max(1, bbox[3] - bbox[1]) + padding * 2
        anchor = (padding - bbox[0], padding - bbox[1])
        image = Image.new("L", (width, height), 0)
        ImageDraw.Draw(image).text(anchor, char, font=font, fill=255, anchor="ls")
        groups = self._connected_groups(image)
        return image, anchor, groups

    @staticmethod
    def _connected_groups(image: Image.Image) -> tuple[tuple[tuple[int, int], ...], ...]:
        width, height = image.size
        pixels = image.load()
        foreground = {(x, y) for y in range(height) for x in range(width) if pixels[x, y] > 3}
        components: list[list[tuple[int, int]]] = []
        while foreground:
            start = foreground.pop()
            stack = [start]
            component = [start]
            while stack:
                x, y = stack.pop()
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    for ny in range(max(0, y - 1), min(height, y + 2)):
                        point = (nx, ny)
                        if point in foreground:
                            foreground.remove(point)
                            stack.append(point)
                            component.append(point)
            components.append(component)
        if len(components) < 2:
            return tuple(tuple(item) for item in components)
        total = sum(len(item) for item in components)
        threshold = max(4, round(total * 0.015))
        major = [item for item in components if len(item) >= threshold]
        minor = [item for item in components if len(item) < threshold]
        if not major:
            major = [max(components, key=len)]
            minor = [item for item in components if item is not major[0]]
        centers = [
            (sum(x for x, _ in item) / len(item), sum(y for _, y in item) / len(item))
            for item in major
        ]
        for item in minor:
            cx = sum(x for x, _ in item) / len(item)
            cy = sum(y for _, y in item) / len(item)
            index = min(
                range(len(major)),
                key=lambda idx: math.dist((cx, cy), centers[idx]),
            )
            major[index].extend(item)
        return tuple(tuple(item) for item in major)

    @staticmethod
    def _perturb_components(
        source: Image.Image,
        groups: tuple[tuple[tuple[int, int], ...], ...],
        rng: random.Random,
        size_px: int,
    ) -> Image.Image:
        if not groups:
            return source.copy()
        result = Image.new("L", source.size, 0)
        original = source.load()
        max_shift = max(1, round(size_px * 0.012))
        for points in groups:
            layer = Image.new("L", source.size, 0)
            pixels = layer.load()
            for x, y in points:
                pixels[x, y] = original[x, y]
            cx = sum(x for x, _ in points) / len(points)
            cy = sum(y for _, y in points) / len(points)
            rotated = layer.rotate(
                rng.uniform(-1.0, 1.0),
                resample=Image.Resampling.BICUBIC,
                center=(cx, cy),
                expand=False,
                fillcolor=0,
            )
            dx = rng.randint(-max_shift, max_shift)
            dy = rng.randint(-max_shift, max_shift)
            moved = Image.new("L", source.size, 0)
            moved.paste(rotated, (dx, dy))
            result = ImageChops.lighter(result, moved)
        return result
