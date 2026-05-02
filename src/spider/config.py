from dataclasses import dataclass
from pathlib import Path

from spider.credentials import Credentials


@dataclass
class RunConfig:
    apk_path: Path
    output_dir: Path
    model: str = "claude-opus-4-7"
    max_steps: int = 500
    device_serial: str | None = None
    image_max_dim: int = 1080
    no_progress_threshold: int = 20
    credentials: Credentials | None = None
