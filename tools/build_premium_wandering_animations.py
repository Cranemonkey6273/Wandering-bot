from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "assets" / "wandering_emojis"
SHEET_DIR = ASSET_ROOT / "animation_keyframes"
STATIC_DIR = ASSET_ROOT / "discord_static"
OUTPUT_DIR = ASSET_ROOT / "premium_animated"
MANIFEST_PATH = ASSET_ROOT / "emoji-manifest.json"
SAMPLER_PATH = ASSET_ROOT / "wandering-premium-animated-sampler.gif"
ZIP_PATH = ROOT / "Wandering-Bot-111-Static-12-Premium-Animated-Pack.zip"
PREMIUM_ZIP_PATH = ROOT / "Wandering-Bot-12-Premium-Animated-Emojis.zip"
DISCORD_LIMIT = 256 * 1024


PREMIUM_IDS = tuple(range(100, 112))
FRAME_DURATIONS = (180, 120, 280, 140)
SAMPLER_LABELS = {
    100: "Middle finger",
    101: "Double middle finger",
    102: "British V sign",
    103: "Wanker gesture",
    104: "Angry finger salute",
    105: "Smug up-yours",
    106: "Tactical Bacon",
    107: "Baked beans",
    108: "Canned peaches",
    109: "Sardines",
    110: "Water bottle",
    111: "Cooked steak",
}


def split_sheet(sheet: Image.Image) -> list[Image.Image]:
    rgba = sheet.convert("RGBA")
    xs = (0, rgba.width // 2, rgba.width)
    ys = (0, rgba.height // 2, rgba.height)
    return [
        rgba.crop((xs[column], ys[row], xs[column + 1], ys[row + 1]))
        for row in range(2)
        for column in range(2)
    ]


def remove_false_checkerboard(frame: Image.Image) -> Image.Image:
    """Remove image-generator checker pixels only when they connect to an edge."""
    rgba = np.asarray(frame.convert("RGBA")).copy()
    if np.mean(rgba[:, :, 3] < 16) > 0.05:
        return Image.fromarray(rgba, "RGBA")

    rgb = rgba[:, :, :3].astype(np.int16)
    candidate = (rgb.min(axis=2) >= 205) & ((rgb.max(axis=2) - rgb.min(axis=2)) <= 18)
    height, width = candidate.shape
    seen = np.zeros((height, width), dtype=np.bool_)
    stack: list[tuple[int, int]] = []

    for x in range(width):
        if candidate[0, x]:
            stack.append((0, x))
        if candidate[height - 1, x]:
            stack.append((height - 1, x))
    for y in range(height):
        if candidate[y, 0]:
            stack.append((y, 0))
        if candidate[y, width - 1]:
            stack.append((y, width - 1))

    while stack:
        y, x = stack.pop()
        if seen[y, x] or not candidate[y, x]:
            continue
        seen[y, x] = True
        if y:
            stack.append((y - 1, x))
        if y + 1 < height:
            stack.append((y + 1, x))
        if x:
            stack.append((y, x - 1))
        if x + 1 < width:
            stack.append((y, x + 1))

    rgba[seen, 3] = 0
    return Image.fromarray(rgba, "RGBA")


def normalise_frames(frames: list[Image.Image], size: int) -> list[Image.Image]:
    cleaned = [remove_false_checkerboard(frame) for frame in frames]
    boxes = [frame.getchannel("A").getbbox() for frame in cleaned]
    if any(box is None for box in boxes):
        raise ValueError("animation keyframe has no visible pixels")

    visible_boxes = [box for box in boxes if box is not None]
    max_width = max(box[2] - box[0] for box in visible_boxes)
    max_height = max(box[3] - box[1] for box in visible_boxes)
    scale = min((size - 8) / max_width, (size - 8) / max_height)

    result: list[Image.Image] = []
    for frame, box in zip(cleaned, visible_boxes):
        crop = frame.crop(box)
        resized = crop.resize(
            (max(1, round(crop.width * scale)), max(1, round(crop.height * scale))),
            Image.Resampling.LANCZOS,
        )
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.alpha_composite(resized, ((size - resized.width) // 2, (size - resized.height) // 2))
        result.append(canvas)
    return result


def paletted_frame(rgba: Image.Image, colors: int) -> Image.Image:
    alpha = rgba.getchannel("A")
    rgb = Image.new("RGB", rgba.size, (0, 0, 0))
    rgb.paste(rgba, mask=alpha)
    frame = rgb.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    palette = frame.getpalette() or []
    palette += [0] * (768 - len(palette))
    palette[255 * 3 : 255 * 3 + 3] = [0, 0, 0]
    frame.putpalette(palette)
    transparent = alpha.point(lambda value: 255 if value <= 24 else 0)
    frame.paste(255, mask=transparent)
    frame.info["transparency"] = 255
    frame.info["disposal"] = 2
    return frame


def write_animation(sheet_path: Path, target: Path) -> None:
    profiles = ((128, 96), (128, 72), (112, 72), (96, 56))
    with Image.open(sheet_path) as sheet:
        source_frames = split_sheet(sheet)

    for size, colors in profiles:
        frames = [paletted_frame(frame, colors) for frame in normalise_frames(source_frames, size)]
        frames[0].save(
            target,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=FRAME_DURATIONS,
            loop=0,
            disposal=2,
            transparency=255,
            optimize=True,
        )
        if target.stat().st_size <= DISCORD_LIMIT:
            return
    raise ValueError(f"could not fit {target.name} below Discord's 256 KiB limit")


def load_font(size: int) -> ImageFont.ImageFont:
    for candidate in (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/segoeui.ttf")):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def create_sampler(paths: list[Path]) -> None:
    columns, rows = 3, 4
    cell_size, label_height = 160, 30
    width, height = columns * cell_size, rows * (cell_size + label_height)
    font = load_font(14)
    sampler_frames: list[Image.Image] = []

    opened = [Image.open(path) for path in paths]
    try:
        for frame_index in range(4):
            canvas = Image.new("RGBA", (width, height), (4, 15, 17, 255))
            draw = ImageDraw.Draw(canvas)
            for index, (path, animation) in enumerate(zip(paths, opened)):
                animation.seek(frame_index)
                frame = animation.convert("RGBA")
                row, column = divmod(index, columns)
                x, y = column * cell_size, row * (cell_size + label_height)
                canvas.alpha_composite(frame, (x + (cell_size - frame.width) // 2, y))
                emoji_id = int(path.name.split("-", 1)[0])
                label = f"{emoji_id}  {SAMPLER_LABELS[emoji_id]}"
                draw.text((x + 8, y + cell_size + 4), label, fill=(231, 238, 236), font=font)
            sampler_frames.append(canvas)
    finally:
        for animation in opened:
            animation.close()

    sampler_frames[0].save(
        SAMPLER_PATH,
        format="GIF",
        save_all=True,
        append_images=sampler_frames[1:],
        duration=FRAME_DURATIONS,
        loop=0,
        disposal=2,
        optimize=True,
    )


def update_manifest(paths: list[Path]) -> None:
    entries = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    by_id = {int(path.name.split("-", 1)[0]): path for path in paths}
    for entry in entries:
        entry.pop("animated", None)
        entry.pop("animated_discord_name", None)
        emoji_id = int(entry["id"])
        if emoji_id in by_id:
            path = by_id[emoji_id]
            entry["premium_animated"] = f"premium_animated/{path.name}"
            entry["premium_animated_discord_name"] = f"{entry['static_discord_name']}_a"
        else:
            entry.pop("premium_animated", None)
            entry.pop("premium_animated_discord_name", None)
    MANIFEST_PATH.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def verify(paths: list[Path]) -> None:
    if len(paths) != 12:
        raise ValueError(f"expected 12 premium animations, found {len(paths)}")
    failures: list[str] = []
    for path in paths:
        with Image.open(path) as image:
            if image.n_frames != 4:
                failures.append(f"{path.name}: expected 4 frames, found {image.n_frames}")
            if image.info.get("loop") != 0:
                failures.append(f"{path.name}: not configured to loop forever")
            if "transparency" not in image.info:
                failures.append(f"{path.name}: missing transparency")
        if path.stat().st_size > DISCORD_LIMIT:
            failures.append(f"{path.name}: {path.stat().st_size} bytes")
    if failures:
        raise ValueError("\n".join(failures))


def create_zip() -> None:
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(STATIC_DIR.glob("*.png")):
            archive.write(path, Path("discord_static") / path.name)
        for path in sorted(OUTPUT_DIR.glob("*.gif")):
            archive.write(path, Path("premium_animated") / path.name)
        for path in (
            ASSET_ROOT / "README.md",
            MANIFEST_PATH,
            ASSET_ROOT / "wandering-emoji-contact-sheet.png",
            SAMPLER_PATH,
        ):
            archive.write(path, path.name)

    with zipfile.ZipFile(PREMIUM_ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(OUTPUT_DIR.glob("*.gif")):
            archive.write(path, path.name)
        archive.write(SAMPLER_PATH, SAMPLER_PATH.name)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sheets = sorted(SHEET_DIR.glob("*-sheet.png"))
    sheets = [path for path in sheets if int(path.name.split("-", 1)[0]) in PREMIUM_IDS]
    if len(sheets) != 12:
        raise ValueError(f"expected 12 premium keyframe sheets, found {len(sheets)}")

    outputs: list[Path] = []
    for sheet in sheets:
        target = OUTPUT_DIR / sheet.name.replace("-sheet.png", "-a.gif")
        write_animation(sheet, target)
        outputs.append(target)

    verify(outputs)
    create_sampler(outputs)
    update_manifest(outputs)
    create_zip()

    print(f"premium_animated={len(outputs)}")
    print(f"largest={max(path.stat().st_size for path in outputs)}")
    print(f"sampler={SAMPLER_PATH}")
    print(f"zip={ZIP_PATH}")
    print(f"premium_zip={PREMIUM_ZIP_PATH}")


if __name__ == "__main__":
    main()
