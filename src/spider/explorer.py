import json
import time
from collections import deque
from pathlib import Path

from spider.action import execute_tool
from spider.config import RunConfig
from spider.device import Device
from spider.elements import parse_hierarchy
from spider.graph import ScreenGraph
from spider.llm import LLM
from spider.observer import Observer
from spider.screen import Screen, compute_phash, compute_structural_hash, screen_id
from spider.storage import append_jsonl, make_run_dir, write_json


def format_elements(elements) -> str:
    if not elements:
        return "(no interactive elements detected)"
    lines = []
    for e in elements:
        if not (e.clickable or e.long_clickable or e.scrollable or e.text or e.content_desc):
            continue
        flags = []
        if e.clickable:
            flags.append("click")
        if e.long_clickable:
            flags.append("long")
        if e.scrollable:
            flags.append("scroll")
        if e.focusable and not e.clickable:
            flags.append("focus")
        flag_str = ",".join(flags) if flags else "label"
        lines.append(f"  {e.id}: {e.label()} [{flag_str}]")
    return "\n".join(lines) if lines else "(no interactive elements)"


def format_history(history) -> str:
    if not history:
        return "(no actions yet)"
    lines = []
    for step_n, screen_before, action_name, screen_after in history:
        same = "→ same screen" if screen_before == screen_after else f"→ {screen_after}"
        lines.append(f"  step {step_n}: on {screen_before}, {action_name} {same}")
    return "\n".join(lines)


def run_exploration(config: RunConfig) -> Path:
    print("[spider] connecting to device...", flush=True)
    device = Device(config.device_serial)

    print(f"[spider] installing {config.apk_path}...", flush=True)
    package = device.install_apk(config.apk_path)
    print(f"[spider] package: {package}", flush=True)

    run_dir = make_run_dir(config.output_dir, package)
    print(f"[spider] run dir: {run_dir}", flush=True)

    write_json(
        run_dir / "config.json",
        {
            "apk_path": str(config.apk_path),
            "package": package,
            "model": config.model,
            "max_steps": config.max_steps,
            "credential_fields": (
                config.credentials.field_names() if config.credentials else []
            ),
        },
    )

    device.launch_app(package)

    graph = ScreenGraph()
    observer = Observer()
    history: deque = deque(maxlen=8)
    llm = LLM(
        model=config.model,
        image_max_dim=config.image_max_dim,
        credentials=config.credentials,
    )

    trace_path = run_dir / "trace.jsonl"
    no_progress_steps = 0
    last_node_count = 0
    prev_screen_id: str | None = None
    prev_action_name: str | None = None
    prev_action_element: str | None = None

    for step in range(config.max_steps):
        # Make sure the app is still in the foreground.
        current_app = device.current_app()
        if current_app.get("package") != package:
            print(
                f"[spider] app left foreground (now {current_app.get('package')}); "
                f"restarting...",
                flush=True,
            )
            device.restart_app(package)
            time.sleep(2)
            current_app = device.current_app()

        png = device.screenshot()
        xml = device.hierarchy()
        phash = compute_phash(png)
        struct = compute_structural_hash(xml)
        sid = screen_id(phash, struct)
        elements = parse_hierarchy(xml)

        screenshot_path = run_dir / "screenshots" / f"{sid}.png"
        hierarchy_path = run_dir / "hierarchies" / f"{sid}.xml"
        if not screenshot_path.exists():
            screenshot_path.write_bytes(png)
        if not hierarchy_path.exists():
            hierarchy_path.write_text(xml)

        screen = Screen(
            id=sid,
            package=current_app.get("package", package),
            activity=current_app.get("activity", ""),
            phash=phash,
            structural_hash=struct,
            screenshot_path=screenshot_path,
            hierarchy_path=hierarchy_path,
            elements=elements,
        )

        canonical_id, is_new = graph.observe(screen)
        screen.id = canonical_id

        # Record the transition from the previous step's action.
        if prev_screen_id is not None and prev_action_name is not None:
            graph.add_transition(
                prev_screen_id, canonical_id, prev_action_name, prev_action_element
            )

        # Stuck detection: are we discovering new screens?
        if len(graph.g.nodes) > last_node_count:
            no_progress_steps = 0
            last_node_count = len(graph.g.nodes)
        else:
            no_progress_steps += 1

        if no_progress_steps >= config.no_progress_threshold:
            print(
                f"[spider] no graph progress for {no_progress_steps} steps — stopping.",
                flush=True,
            )
            break

        if step > 5 and graph.is_complete():
            print("[spider] graph complete — stopping.", flush=True)
            break

        # Ask the LLM for the next action.
        try:
            tool_name, tool_input, reasoning, usage = llm.choose_action(
                screenshot_png=png,
                elements_text=format_elements(screen.elements),
                graph_summary=graph.summarize(current_screen_id=screen.id),
                history_text=format_history(history),
                observations_summary=observer.summary(),
                activity=screen.activity,
                package=screen.package,
                current_screen_id=screen.id,
            )
        except Exception as e:
            print(f"[spider] LLM call failed at step {step}: {e}", flush=True)
            append_jsonl(
                trace_path,
                {"step": step, "error": f"llm_call_failed: {e}", "screen_id": screen.id},
            )
            time.sleep(2)
            continue

        # Execute it.
        try:
            result = execute_tool(
                tool_name,
                dict(tool_input),
                device=device,
                observer=observer,
                graph=graph,
                current_screen=screen,
                credentials=config.credentials,
            )
        except Exception as e:
            result = {"success": False, "error": f"execute_tool failed: {e}"}

        cache_read = usage.get("cache_read_input_tokens", 0)
        new_marker = "[NEW]" if is_new else "    "
        elem_label = tool_input.get("element_id") or ""
        print(
            f"[spider] step {step:03d} {new_marker} {screen.id} "
            f"| {tool_name}{(' '+elem_label) if elem_label else ''} "
            f"| cache_read={cache_read}",
            flush=True,
        )

        append_jsonl(
            trace_path,
            {
                "step": step,
                "screen_id": screen.id,
                "is_new_screen": is_new,
                "tool": tool_name,
                "input": dict(tool_input),
                "reasoning": reasoning[:1000],
                "usage": usage,
                "success": result.get("success", False),
                "error": result.get("error"),
            },
        )

        history.append((step, screen.id, tool_name, screen.id))
        prev_screen_id = screen.id
        prev_action_name = tool_name
        prev_action_element = tool_input.get("element_id")

        if result.get("terminates_run"):
            print("[spider] LLM signalled completion — stopping.", flush=True)
            break

    # Persist final state.
    write_json(run_dir / "graph.json", graph.to_dict())
    write_json(run_dir / "observations.json", observer.to_dict())

    print(
        f"[spider] exploration done. {len(graph.g.nodes)} screens, "
        f"{graph.g.number_of_edges()} transitions.",
        flush=True,
    )
    return run_dir


def generate_prd(run_dir: Path, model: str = "claude-opus-4-7") -> Path:
    config = json.loads((run_dir / "config.json").read_text())
    graph = json.loads((run_dir / "graph.json").read_text())
    observations = json.loads((run_dir / "observations.json").read_text())

    llm = LLM(model=model)
    print("[spider] synthesizing PRD (this may take a few minutes)...", flush=True)
    prd = llm.synthesize_prd(graph, observations, config)
    prd_path = run_dir / "prd.md"
    prd_path.write_text(prd)
    print(f"[spider] PRD written: {prd_path} ({len(prd)} chars)", flush=True)
    return prd_path
