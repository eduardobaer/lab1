from pathlib import Path

import click
from dotenv import load_dotenv

from spider.config import RunConfig
from spider.explorer import generate_prd, run_exploration

load_dotenv()


@click.group()
def cli():
    """Spider — Android app documentation crawler."""


@cli.command()
@click.argument("apk_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--device", "device_serial", default=None, help="adb device serial (default: auto-detect).")
@click.option("--max-steps", default=500, type=int, help="Maximum exploration steps.")
@click.option("--model", default="claude-opus-4-7", help="Anthropic model ID.")
@click.option("--output-dir", default="runs", type=click.Path(path_type=Path))
@click.option(
    "--no-progress-threshold",
    default=20,
    type=int,
    help="Stop after N consecutive steps without discovering a new screen.",
)
@click.option("--skip-prd", is_flag=True, help="Skip PRD synthesis (run exploration only).")
def explore(apk_path, device_serial, max_steps, model, output_dir, no_progress_threshold, skip_prd):
    """Explore an APK and produce a PRD."""
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    config = RunConfig(
        apk_path=apk_path.resolve(),
        output_dir=output_dir,
        model=model,
        max_steps=max_steps,
        device_serial=device_serial,
        no_progress_threshold=no_progress_threshold,
    )
    run_dir = run_exploration(config)
    if not skip_prd:
        generate_prd(run_dir, model=model)


@cli.command()
@click.argument("run_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--model", default="claude-opus-4-7", help="Anthropic model ID.")
def prd(run_dir, model):
    """Regenerate the PRD from existing run data."""
    generate_prd(run_dir.resolve(), model=model)


if __name__ == "__main__":
    cli()
