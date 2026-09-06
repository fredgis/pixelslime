"""Build and check the fixed 36-card selective-holography concept package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "cards"
SIZE = (822, 1122)
DPI = 300
FILES = (
    "front.png",
    "back.png",
    "holo-mask.png",
    "holo-mask.svg",
    "white-ink-mask.png",
    "white-ink-mask.svg",
    "qpmn-white-layer-mask.png",
    "qpmn-white-layer-mask.svg",
    "preview.webp",
)
CREAM = "#fff8eb"
INK = "#30213f"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_inputs() -> tuple[list[dict], dict]:
    with (SOURCE / "manifest.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    masks = json.loads((ROOT / "mask-definitions.json").read_text(encoding="utf-8"))
    if len(rows) != 36 or [int(row["slot"]) for row in rows] != list(range(1, 37)):
        raise ValueError("Expected the fixed, ordered 36-card source snapshot.")
    if set(masks) != {row["card_id"] for row in rows}:
        raise ValueError("Mask definitions must match all 36 source card IDs exactly.")
    for row in rows:
        for field in ("recto_file", "verso_file"):
            value = row[field]
            if Path(value).name != value or not value.endswith(".png"):
                raise ValueError(f"Invalid source filename: {value}")
        definition = masks[row["card_id"]]
        if not definition["foil"] or not isinstance(definition["notes"], str):
            raise ValueError(f"Missing foil geometry or description: {row['card_id']}")
        for group in ("foil", "opaque"):
            for shape in definition[group]:
                validate_shape(shape)
    return rows, masks


def validate_shape(shape: dict) -> None:
    kind = shape["type"]
    if kind == "polygon":
        points = shape["points"]
        if len(points) < 3:
            raise ValueError(f"A polygon needs at least three points: {shape}")
    elif kind == "rect":
        x, y, width, height = (shape[key] for key in ("x", "y", "width", "height"))
        if width <= 0 or height <= 0:
            raise ValueError(f"Empty rectangle: {shape}")
        points = [[x, y], [x + width, y + height]]
        radius = shape.get("radius", 0)
        if not isinstance(radius, int) or radius < 0 or radius * 2 > min(width, height):
            raise ValueError(f"Invalid corner radius: {shape}")
    elif kind == "ellipse":
        cx, cy, rx, ry = (shape[key] for key in ("cx", "cy", "rx", "ry"))
        if rx <= 0 or ry <= 0:
            raise ValueError(f"Empty ellipse: {shape}")
        points = [[cx - rx, cy - ry], [cx + rx, cy + ry]]
    else:
        raise ValueError(f"Unsupported mask shape: {kind}")
    for point in points:
        if len(point) != 2 or any(type(value) is not int for value in point):
            raise ValueError(f"Coordinates must be integer pixel pairs: {point}")
        if not 0 <= point[0] <= SIZE[0] or not 0 <= point[1] <= SIZE[1]:
            raise ValueError(f"Mask geometry exceeds the source canvas: {point}")


def paint(draw: ImageDraw.ImageDraw, shape: dict, fill: int) -> None:
    kind = shape["type"]
    if kind == "polygon":
        draw.polygon([tuple(point) for point in shape["points"]], fill=fill)
    elif kind == "rect":
        x, y = shape["x"], shape["y"]
        box = (x, y, x + shape["width"] - 1, y + shape["height"] - 1)
        draw.rounded_rectangle(box, radius=shape.get("radius", 0), fill=fill)
    elif kind == "ellipse":
        cx, cy, rx, ry = (shape[key] for key in ("cx", "cy", "rx", "ry"))
        draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=fill)
    else:
        raise ValueError(f"Unsupported mask shape: {kind}")


def raster_mask(definition: dict) -> Image.Image:
    image = Image.new("L", SIZE, 0)
    draw = ImageDraw.Draw(image)
    for shape in definition["foil"]:
        paint(draw, shape, 255)
    for shape in definition["opaque"]:
        paint(draw, shape, 0)
    return image


def svg_shape(parent: ET.Element, shape: dict, fill: str) -> None:
    kind = shape["type"]
    if kind == "polygon":
        attributes = {"points": " ".join(f"{x},{y}" for x, y in shape["points"])}
    elif kind == "rect":
        attributes = {key: str(shape[key]) for key in ("x", "y", "width", "height")}
        if shape.get("radius"):
            attributes["rx"] = str(shape["radius"])
    elif kind == "ellipse":
        attributes = {key: str(shape[key]) for key in ("cx", "cy", "rx", "ry")}
    else:
        raise ValueError(f"Unsupported mask shape: {kind}")
    ET.SubElement(parent, kind, {**attributes, "fill": fill})


def svg_mask(card_id: str, definition: dict, white_ink: bool, qpmn: bool = False) -> str:
    if qpmn and white_ink:
        raise ValueError("QPMN's black-means-white-ink convention requires the holo-mask polarity.")
    root = ET.Element("svg", {
        "xmlns": "http://www.w3.org/2000/svg",
        "width": f"{SIZE[0] / DPI * 25.4:.3f}mm",
        "height": f"{SIZE[1] / DPI * 25.4:.3f}mm",
        "viewBox": f"0 0 {SIZE[0]} {SIZE[1]}",
    })
    label = "QPMN white-layer" if qpmn else ("white ink" if white_ink else "holographic area")
    ET.SubElement(root, "title").text = f"{card_id} - {label} concept mask"
    if qpmn:
        description = "Black designates the opaque white-ink pass; white designates no white ink, exposing foil. Ask QPMN prepress to prepare its required K100 separation."
    elif white_ink:
        description = "White means opaque white ink; black means exposed holographic stock."
    else:
        description = "White means holographic area; black means no holographic effect."
    ET.SubElement(root, "desc").text = description + " Editable design intent only; adapt to the printer's template and prepress requirements."
    base, foil, opaque = ("white", "black", "white") if white_ink else ("black", "white", "black")
    ET.SubElement(root, "rect", {"width": str(SIZE[0]), "height": str(SIZE[1]), "fill": base})
    for shape in definition["foil"]:
        svg_shape(root, shape, foil)
    for shape in definition["opaque"]:
        svg_shape(root, shape, opaque)
    return ET.tostring(root, encoding="unicode") + "\n"


def folder_for(row: dict) -> Path:
    return ROOT / "cards" / row["recto_file"].removesuffix("-recto.png")


def title_for(row: dict, definition: dict) -> str:
    return definition.get("display_name", row["name"])


def preview(row: dict, definition: dict, folder: Path, mask: Image.Image) -> None:
    thumb = (246, 336)
    canvas = Image.new("RGB", (814, 438), CREAM)
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=18)
    small = ImageFont.load_default(size=13)
    draw.text((20, 15), f"{row['card_id']} / {title_for(row, definition)}", fill=INK, font=font)
    labels = ("FRONT / ORIGINAL", "BACK / NO HOLO", "MASK / WHITE = HOLO")
    with Image.open(folder / "front.png") as front, Image.open(folder / "back.png") as back:
        images = (front.convert("RGB"), back.convert("RGB"), mask.convert("RGB"))
        for index, (image, label) in enumerate(zip(images, labels)):
            x = 20 + index * 264
            draw.text((x, 45), label, fill=INK, font=small)
            sampling = Image.Resampling.NEAREST if index == 2 else Image.Resampling.LANCZOS
            canvas.paste(image.resize(thumb, sampling), (x, 67))
    draw.text((20, 416), "CONCEPT MASK / printer prepress required / not an upload sheet", fill=INK, font=small)
    canvas.save(folder / "preview.webp", quality=88, method=6)


def contact_sheets(rows: list[dict], masks: dict) -> None:
    destination = ROOT / "previews"
    destination.mkdir(exist_ok=True)
    font = ImageFont.load_default(size=14)
    heading = ImageFont.load_default(size=24)
    for start in range(0, len(rows), 9):
        canvas = Image.new("RGB", (1128, 930), CREAM)
        draw = ImageDraw.Draw(canvas)
        draw.text((26, 18), f"PIXELSLIME / HOLO MASKS / {start + 1:02d}-{start + 9:02d}", fill=INK, font=heading)
        draw.text((26, 51), "Original front + holographic-area mask (white = holo). All are prepress concepts.", fill=INK, font=font)
        for index, row in enumerate(rows[start:start + 9]):
            x = 25 + (index % 3) * 368
            y = 87 + (index // 3) * 278
            folder = folder_for(row)
            label = f"{row['slot']}. {row['card_id']} / {title_for(row, masks[row['card_id']])}"
            draw.text((x, y), label, fill=INK, font=font)
            with Image.open(folder / "front.png") as front, Image.open(folder / "holo-mask.png") as mask:
                canvas.paste(front.convert("RGB").resize((164, 224), Image.Resampling.LANCZOS), (x, y + 25))
                canvas.paste(mask.convert("RGB").resize((164, 224), Image.Resampling.NEAREST), (x + 176, y + 25))
        canvas.save(destination / f"masks-{start + 1:02d}-{start + 9:02d}.webp", quality=88, method=6)


def build(rows: list[dict], masks: dict) -> None:
    records = []
    for row in rows:
        definition = masks[row["card_id"]]
        folder = folder_for(row)
        folder.mkdir(parents=True, exist_ok=True)
        sources = {
            "front": SOURCE / "print" / "fronts" / row["recto_file"],
            "back": SOURCE / "print" / "backs" / row["verso_file"],
        }
        for face, source in sources.items():
            with Image.open(source) as image:
                if image.size != SIZE:
                    raise ValueError(f"Unexpected source dimensions: {source}")
            shutil.copyfile(source, folder / f"{face}.png")
        holo = raster_mask(definition)
        if holo.getextrema() != (0, 255):
            raise ValueError(f"The holo mask is empty or covers the entire card: {row['card_id']}")
        holo.save(folder / "holo-mask.png", dpi=(DPI, DPI), optimize=True)
        ImageOps.invert(holo).save(folder / "white-ink-mask.png", dpi=(DPI, DPI), optimize=True)
        shutil.copyfile(folder / "holo-mask.png", folder / "qpmn-white-layer-mask.png")
        for name, white_ink, qpmn in (
            ("holo-mask", False, False),
            ("white-ink-mask", True, False),
            ("qpmn-white-layer-mask", False, True),
        ):
            (folder / f"{name}.svg").write_text(svg_mask(row["card_id"], definition, white_ink, qpmn), encoding="utf-8")
        preview(row, definition, folder, holo)
        records.append({
            "slot": row["slot"], "card_id": row["card_id"],
            "name": title_for(row, definition), "source_name": row["name"],
            "kind": row["kind"], "rarity": row["rarity"],
            "source_date": row["mint_date"], "profile_url": row["profile_url"],
            **{name.replace("-", "_").replace(".", "_"): (folder / name).relative_to(ROOT).as_posix() for name in FILES},
            "front_sha256": sha256(sources["front"]), "back_sha256": sha256(sources["back"]),
            "holo_percent": f"{holo.histogram()[255] / (SIZE[0] * SIZE[1]) * 100:.2f}",
            "mask_status": "concept-awaiting-prepress", "notes": definition["notes"],
        })
    with (ROOT / "manifest.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    contact_sheets(rows, masks)


def check(rows: list[dict], masks: dict) -> None:
    expected_folders = {folder_for(row).name for row in rows}
    actual_folders = {folder.name for folder in (ROOT / "cards").iterdir() if folder.is_dir()}
    if actual_folders != expected_folders:
        raise ValueError("Per-card folders do not match the 36-card manifest.")
    with (ROOT / "manifest.csv").open(encoding="utf-8", newline="") as stream:
        records = list(csv.DictReader(stream))
    if [record["card_id"] for record in records] != [row["card_id"] for row in rows]:
        raise ValueError("Generated manifest is incomplete or out of order.")
    for row, record in zip(rows, records):
        folder = folder_for(row)
        if {item.name for item in folder.iterdir()} != set(FILES):
            raise ValueError(f"Missing or unexpected files: {folder}")
        for face, source_dir, key in (("front", "fronts", "recto_file"), ("back", "backs", "verso_file")):
            original_hash = sha256(SOURCE / "print" / source_dir / row[key])
            if sha256(folder / f"{face}.png") != original_hash or record[f"{face}_sha256"] != original_hash:
                raise ValueError(f"The original {face} was changed: {row['card_id']}")
        with Image.open(folder / "holo-mask.png") as holo, Image.open(folder / "white-ink-mask.png") as white:
            if holo.size != SIZE or white.size != SIZE or holo.mode != "L" or white.mode != "L":
                raise ValueError(f"Mask dimensions or mode are incorrect: {row['card_id']}")
            if set(holo.tobytes()) != {0, 255} or set(white.tobytes()) != {0, 255}:
                raise ValueError(f"Mask must be pure binary black/white: {row['card_id']}")
            if ImageOps.invert(holo).tobytes() != white.tobytes():
                raise ValueError(f"Mask conventions are not exact inverses: {row['card_id']}")
            if holo.tobytes() != raster_mask(masks[row["card_id"]]).tobytes():
                raise ValueError(f"PNG and editable mask definition differ: {row['card_id']}")
            for image in (holo, white):
                if any(abs(value - DPI) > .1 for value in image.info.get("dpi", (0, 0))):
                    raise ValueError(f"Missing 300 dpi mask metadata: {row['card_id']}")
        if sha256(folder / "qpmn-white-layer-mask.png") != sha256(folder / "holo-mask.png"):
            raise ValueError(f"Incorrect QPMN white-layer polarity: {row['card_id']}")
        for name, white_ink, qpmn in (
            ("holo-mask", False, False),
            ("white-ink-mask", True, False),
            ("qpmn-white-layer-mask", False, True),
        ):
            if (folder / f"{name}.svg").read_text(encoding="utf-8") != svg_mask(row["card_id"], masks[row["card_id"]], white_ink, qpmn):
                raise ValueError(f"SVG differs from the editable geometry: {row['card_id']}")
        for name in FILES:
            if record[name.replace("-", "_").replace(".", "_")] != (folder / name).relative_to(ROOT).as_posix():
                raise ValueError(f"Invalid manifest link: {row['card_id']} / {name}")
    print("36 fronts + 36 backs unchanged; 36 aligned holo/white-ink/QPMN PNG+SVG mask sets; 36 previews.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check existing outputs without rewriting files.")
    arguments = parser.parse_args()
    source_rows, definitions = load_inputs()
    if not arguments.check:
        build(source_rows, definitions)
    check(source_rows, definitions)
