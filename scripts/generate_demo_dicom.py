"""Generate small public-domain-style demo DICOM sample pack (PNG frames + stubs).

Creates ``demo_data/dicom/{modality}_{n}/`` with:
  - frame_0.png … (viewer-ready)
  - sample.dcm (minimal binary stub for metadata/download demos)

Run: ``python -m scripts.generate_demo_dicom``
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "demo_data" / "dicom"

SAMPLES = [
    ("CT", "Chest CT", (30, 90, 140)),
    ("CT", "Abdomen CT", (40, 70, 100)),
    ("CT", "Head CT", (50, 50, 80)),
    ("MR", "Brain MRI", (80, 40, 100)),
    ("MR", "Spine MRI", (60, 50, 110)),
    ("MR", "Knee MRI", (70, 60, 90)),
    ("CR", "Chest X-ray", (120, 120, 130)),
    ("CR", "Hand X-ray", (110, 110, 120)),
    ("DX", "Pelvis X-ray", (100, 105, 115)),
    ("US", "Abdominal US", (20, 100, 140)),
]


def _png_bytes(width: int, height: int, rgb: tuple[int, int, int], pattern: int = 0) -> bytes:
    rows = []
    for y in range(height):
        row = bytearray()
        row.append(0)
        for x in range(width):
            if pattern == 0:
                # radial gradient
                cx, cy = width / 2, height / 2
                d = math.hypot(x - cx, y - cy) / (width / 2)
                f = max(0.0, 1.0 - d)
            elif pattern == 1:
                f = 0.5 + 0.5 * math.sin((x + y + pattern) / 8)
            else:
                f = ((x // 8) + (y // 8)) % 2
            r = min(255, int(rgb[0] * (0.4 + 0.6 * f)))
            g = min(255, int(rgb[1] * (0.4 + 0.6 * f)))
            b = min(255, int(rgb[2] * (0.4 + 0.6 * f)))
            row.extend((r, g, b))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def _dcm_stub(modality: str, description: str, study_uid: str, series_uid: str, sop_uid: str) -> bytes:
    """Minimal non-standard DICOM-like stub (not for clinical use)."""
    meta = (
        f"DEMO_DICOM\nModality={modality}\nDescription={description}\n"
        f"StudyInstanceUID={study_uid}\nSeriesInstanceUID={series_uid}\n"
        f"SOPInstanceUID={sop_uid}\n"
    ).encode("ascii")
    # Prepend a DICOM preamble + DICM magic so tools recognize the container.
    preamble = b"\x00" * 128 + b"DICM"
    return preamble + meta


def generate(out_dir: Path = OUT) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for idx, (modality, description, rgb) in enumerate(SAMPLES, start=1):
        folder = out_dir / f"{modality.lower()}_{idx:02d}"
        folder.mkdir(parents=True, exist_ok=True)
        study_uid = f"1.2.826.0.1.3680043.8.498.demo.{idx}.1"
        series_uid = f"1.2.826.0.1.3680043.8.498.demo.{idx}.2"
        sop_uid = f"1.2.826.0.1.3680043.8.498.demo.{idx}.3"
        png = folder / "frame_0.png"
        png.write_bytes(_png_bytes(256, 256, rgb, pattern=idx % 3))
        dcm = folder / "sample.dcm"
        dcm.write_bytes(_dcm_stub(modality, description, study_uid, series_uid, sop_uid))
        meta = folder / "meta.txt"
        meta.write_text(
            f"modality={modality}\ndescription={description}\n"
            f"study_uid={study_uid}\nseries_uid={series_uid}\nsop_uid={sop_uid}\n",
            encoding="utf-8",
        )
        created.append(folder)
    (out_dir / "README.md").write_text(
        "# Demo DICOM sample pack\n\n"
        "Synthetic PNG frames + DICOM stubs for MedInsight buyer demo.\n"
        "Not for clinical use. Regenerate with `python -m scripts.generate_demo_dicom`.\n",
        encoding="utf-8",
    )
    return created


def main() -> int:
    paths = generate()
    print(f"Generated {len(paths)} samples under {OUT}")
    for p in paths:
        print(" ", p.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
