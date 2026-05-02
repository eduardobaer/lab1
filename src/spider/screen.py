import hashlib
import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import imagehash
from PIL import Image


@dataclass
class Screen:
    id: str
    package: str
    activity: str
    phash: str
    structural_hash: str
    screenshot_path: Path
    hierarchy_path: Path
    elements: list = field(default_factory=list)


def compute_phash(image_bytes: bytes) -> str:
    img = Image.open(BytesIO(image_bytes))
    return str(imagehash.phash(img))


def compute_structural_hash(xml_text: str) -> str:
    """Hash the UI tree's structure, ignoring values that drift across captures
    (bounds shift mid-animation, indices change as siblings re-order)."""
    normalized = re.sub(r'bounds="[^"]*"', "", xml_text)
    normalized = re.sub(r'index="\d+"', "", normalized)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def screen_id(phash: str, structural_hash: str) -> str:
    return f"{phash[:8]}-{structural_hash[:8]}"


def phash_distance(a: str, b: str) -> int:
    h1 = imagehash.hex_to_hash(a)
    h2 = imagehash.hex_to_hash(b)
    return h1 - h2
