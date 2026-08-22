from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
MASTER_DIR = ROOT / "assets" / "wandering_emojis" / "static"
STATIC_DIR = ROOT / "assets" / "wandering_emojis" / "discord_static"
ANIMATED_DIR = ROOT / "assets" / "wandering_emojis" / "animated"
PREVIEW_PATH = ROOT / "assets" / "wandering_emojis" / "wandering-emoji-contact-sheet.png"
MANIFEST_PATH = ROOT / "assets" / "wandering_emojis" / "emoji-manifest.json"
DISCORD_LIMIT = 256 * 1024


SHAKE_WORDS = {
    "angry", "furious", "panic", "warning", "ban-hammer", "zombie",
    "middle-finger", "wanker", "up-yours", "no", "sick", "vomiting",
}
PULSE_WORDS = {
    "heart", "love", "check", "safe-zone", "radar", "money", "trophy",
    "crown", "leaderboard", "shop", "sun", "moon", "medic", "battery",
}
TILT_WORDS = {
    "wave", "salute", "point", "peace", "clap", "prayer", "thinking",
    "british-v-sign", "okay", "thumbs-up",
}
SLEEP_WORDS = {"sleeping", "tired", "sad", "defeated", "pleading"}
TRAVEL_WORDS = {"car", "boat", "helicopter", "airdrop", "rain", "sakhal-snow"}


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    rgba = image.convert("RGBA")
    bbox = rgba.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("image has no visible pixels")
    return bbox


def fit_master(master: Image.Image, size: int, inset: int) -> Image.Image:
    rgba = master.convert("RGBA")
    cropped = rgba.crop(alpha_bbox(rgba))
    max_side = size - inset * 2
    scale = min(max_side / cropped.width, max_side / cropped.height)
    fitted = cropped.resize(
        (max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - fitted.width) // 2
    y = (size - fitted.height) // 2
    canvas.alpha_composite(fitted, (x, y))
    return canvas


def save_static(master_path: Path) -> Path:
    target = STATIC_DIR / master_path.name
    with Image.open(master_path) as master:
        image = fit_master(master, 128, 4)
        image.save(target, format="PNG", optimize=True, compress_level=9)
    if target.stat().st_size > DISCORD_LIMIT:
        raise ValueError(f"static export exceeds Discord limit: {target.name}")
    return target


def motion_kind(slug: str) -> str:
    if any(word in slug for word in SHAKE_WORDS):
        return "shake"
    if any(word in slug for word in PULSE_WORDS):
        return "pulse"
    if any(word in slug for word in TILT_WORDS):
        return "tilt"
    if any(word in slug for word in SLEEP_WORDS):
        return "sleep"
    if any(word in slug for word in TRAVEL_WORDS):
        return "travel"
    if any(word in slug for word in ("beans", "bacon", "peaches", "sardines", "water-bottle", "steak", "canteen", "coffee", "tea", "beer", "pizza", "burger", "candy")):
        return "bounce"
    return "bob"


def transform_frame(base: Image.Image, kind: str, index: int, count: int) -> Image.Image:
    phase = 2 * math.pi * index / count
    dx = 0
    dy = 0
    angle = 0.0
    scale = 1.0

    if kind == "shake":
        dx = (-2, 2, -1, 2, -2, 1, 0, 1)[index % 8]
        angle = (-1.8, 1.8, -1.0, 1.5, -1.5, 1.0, 0.0, 0.7)[index % 8]
    elif kind == "pulse":
        scale = 1.0 + 0.045 * (0.5 + 0.5 * math.sin(phase - math.pi / 2))
    elif kind == "tilt":
        angle = 2.6 * math.sin(phase)
        dy = round(-1.5 * math.sin(phase))
    elif kind == "sleep":
        angle = -1.2 + 1.2 * math.sin(phase)
        dy = round(1.5 + 1.2 * math.sin(phase))
    elif kind == "travel":
        dx = round(2.5 * math.sin(phase))
        dy = round(-1.5 * abs(math.sin(phase)))
        angle = 0.8 * math.sin(phase)
    elif kind == "bounce":
        dy = round(-3.5 * abs(math.sin(phase)))
        scale = 1.0 + 0.018 * abs(math.sin(phase))
    else:
        dy = round(-2.2 * math.sin(phase))
        angle = 0.7 * math.sin(phase)

    frame = base
    if scale != 1.0:
        resized = base.resize(
            (max(1, round(base.width * scale)), max(1, round(base.height * scale))),
            Image.Resampling.LANCZOS,
        )
        scaled = Image.new("RGBA", base.size, (0, 0, 0, 0))
        scaled.alpha_composite(
            resized,
            ((base.width - resized.width) // 2, (base.height - resized.height) // 2),
        )
        frame = scaled
    if angle:
        frame = frame.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False)
    moved = Image.new("RGBA", base.size, (0, 0, 0, 0))
    moved.alpha_composite(frame, (dx, dy))
    return moved


def gif_frame(rgba: Image.Image, colors: int) -> Image.Image:
    alpha = rgba.getchannel("A")
    rgb = Image.new("RGB", rgba.size, (0, 0, 0))
    rgb.paste(rgba, mask=alpha)
    paletted = rgb.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    palette = paletted.getpalette() or []
    palette += [0] * (768 - len(palette))
    palette[255 * 3 : 255 * 3 + 3] = [0, 0, 0]
    paletted.putpalette(palette)
    transparent = alpha.point(lambda value: 255 if value <= 28 else 0)
    paletted.paste(255, mask=transparent)
    paletted.info["transparency"] = 255
    paletted.info["disposal"] = 2
    return paletted


def write_gif(static_path: Path, size: int, count: int, colors: int, target: Path) -> None:
    with Image.open(static_path) as source:
        base = fit_master(source, size, max(2, round(size * 0.04)))
    kind = motion_kind(static_path.stem)
    frames = [gif_frame(transform_frame(base, kind, i, count), colors) for i in range(count)]
    frames[0].save(
        target,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=110,
        loop=0,
        disposal=2,
        transparency=255,
        optimize=False,
    )


def save_animated(static_path: Path) -> Path:
    target = ANIMATED_DIR / f"{static_path.stem}-a.gif"
    profiles = (
        (128, 8, 80),
        (112, 7, 64),
        (96, 6, 48),
        (80, 5, 40),
    )
    for size, count, colors in profiles:
        write_gif(static_path, size, count, colors, target)
        if target.stat().st_size <= DISCORD_LIMIT:
            return target
    raise ValueError(f"animated export exceeds Discord limit: {target.name}")


def load_font(size: int) -> ImageFont.ImageFont:
    candidates = (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
    )
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def create_contact_sheet(static_paths: list[Path]) -> None:
    columns = 9
    cell_w, cell_h = 150, 158
    rows = math.ceil(len(static_paths) / columns)
    sheet = Image.new("RGB", (columns * cell_w, rows * cell_h), (5, 15, 16))
    draw = ImageDraw.Draw(sheet)
    label_font = load_font(14)
    number_font = load_font(13)

    for index, path in enumerate(static_paths):
        row, column = divmod(index, columns)
        x, y = column * cell_w, row * cell_h
        with Image.open(path) as image:
            thumb = image.convert("RGBA").resize((112, 112), Image.Resampling.LANCZOS)
        tile = Image.new("RGBA", (cell_w - 8, cell_h - 8), (8, 27, 29, 245))
        tile.alpha_composite(thumb, ((tile.width - 112) // 2, 4))
        sheet.paste(tile.convert("RGB"), (x + 4, y + 4))
        number, slug = path.stem.split("-", 1)
        draw.text((x + 10, y + 121), number, fill=(255, 172, 58), font=number_font)
        label = slug if len(slug) <= 16 else slug[:15] + "…"
        draw.text((x + 36, y + 120), label, fill=(226, 238, 236), font=label_font)

    sheet.save(PREVIEW_PATH, format="PNG", optimize=True)


def category_for(number: int) -> str:
    if number <= 49:
        return "reactions"
    if number <= 56:
        return "food-and-drink"
    if number <= 96:
        return "dayz-and-survival"
    if number <= 99:
        return "map-reflections"
    if number <= 105:
        return "adult-reactions"
    return "dayz-food-bonus"


def create_manifest(static_paths: list[Path]) -> None:
    entries = []
    for path in static_paths:
        number_text, slug = path.stem.split("-", 1)
        number = int(number_text)
        entry = {
            "id": number,
            "slug": slug,
            "static_discord_name": slug.replace("-", "_"),
            "category": category_for(number),
            "static": f"discord_static/{path.name}",
        }
        if 100 <= number <= 111:
            entry["premium_animated_discord_name"] = f"{slug.replace('-', '_')}_a"
            entry["premium_animated"] = f"premium_animated/{path.stem}-a.gif"
        entries.append(entry)
    MANIFEST_PATH.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def verify(static_paths: list[Path]) -> None:
    if len(static_paths) != 111:
        raise ValueError(f"expected 111 static exports, got {len(static_paths)}")
    failures: list[str] = []
    for path in static_paths:
        with Image.open(path) as image:
            if image.size != (128, 128):
                failures.append(f"{path.name}: static dimensions {image.size}")
            if image.convert("RGBA").getchannel("A").getextrema()[0] == 255:
                failures.append(f"{path.name}: missing transparency")
        if path.stat().st_size > DISCORD_LIMIT:
            failures.append(f"{path.name}: {path.stat().st_size} bytes")
    if failures:
        raise ValueError("\n".join(failures))


def main() -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    masters = sorted(MASTER_DIR.glob("*.png"))
    if len(masters) != 111:
        raise ValueError(f"expected 111 masters, found {len(masters)}")

    static_paths = [save_static(path) for path in masters]
    verify(static_paths)
    create_contact_sheet(static_paths)
    create_manifest(static_paths)

    max_static = max(path.stat().st_size for path in static_paths)
    print(f"static={len(static_paths)}")
    print(f"largest_static={max_static}")
    print(f"preview={PREVIEW_PATH}")


if __name__ == "__main__":
    main()
