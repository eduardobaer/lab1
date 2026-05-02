import json
from datetime import datetime
from pathlib import Path


def make_run_dir(output_dir: Path, package: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = output_dir / f"{ts}-{package}"
    (run_dir / "screenshots").mkdir(parents=True, exist_ok=True)
    (run_dir / "hierarchies").mkdir(parents=True, exist_ok=True)
    return run_dir


def append_jsonl(path: Path, record: dict) -> None:
    with path.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, default=str))
