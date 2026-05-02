"""Action execution.

Tool calls coming from the LLM are dispatched here. We keep this as a single
function rather than a class hierarchy — there's no shared state worth
encapsulating, just a switch on tool name.
"""

import time


def execute_tool(
    name: str,
    params: dict,
    *,
    device,
    observer,
    graph,
    current_screen,
    credentials=None,
) -> dict:
    """Execute a tool call. Returns dict with at least 'success' (bool);
    optionally 'error' (str) and 'terminates_run' (bool)."""

    def _resolve_target():
        eid = params.get("element_id")
        if eid:
            elem = next((e for e in current_screen.elements if e.id == eid), None)
            if elem is None:
                return None, None, eid, f"Unknown element {eid}"
            return elem.center[0], elem.center[1], eid, None
        x, y = params.get("x"), params.get("y")
        if x is None or y is None:
            return None, None, None, "Missing element_id or x/y"
        return int(x), int(y), None, None

    if name == "tap":
        x, y, eid, err = _resolve_target()
        if err:
            return {"success": False, "error": err}
        if eid:
            graph.mark_explored(current_screen.id, eid)
        device.tap(x, y)
        time.sleep(1.0)
        return {"success": True}

    if name == "long_press":
        x, y, eid, err = _resolve_target()
        if err:
            return {"success": False, "error": err}
        if eid:
            graph.mark_explored(current_screen.id, eid)
        device.long_press(x, y)
        time.sleep(1.0)
        return {"success": True}

    if name == "swipe":
        device.swipe(params.get("direction", "up"))
        time.sleep(0.8)
        return {"success": True}

    if name == "type_text":
        device.type_text(params.get("text", ""))
        time.sleep(0.5)
        return {"success": True}

    if name == "press_back":
        device.press_back()
        time.sleep(1.0)
        return {"success": True}

    if name == "wait":
        time.sleep(min(int(params.get("seconds", 2)), 10))
        return {"success": True}

    if name == "record_screen":
        observer.record_screen(
            current_screen.id,
            params.get("name", ""),
            params.get("description", ""),
            params.get("capabilities", []) or [],
        )
        return {"success": True}

    if name == "record_flow":
        observer.record_flow(
            params.get("name", ""),
            params.get("description", ""),
            params.get("screens", []) or [],
        )
        return {"success": True}

    if name == "record_note":
        observer.record_note(current_screen.id, params.get("note", ""))
        return {"success": True}

    if name == "mark_screen_done":
        graph.mark_screen_done(current_screen.id)
        return {"success": True}

    if name == "mark_app_fully_explored":
        return {"success": True, "terminates_run": True}

    if name == "fill_credential":
        if credentials is None or not credentials:
            return {"success": False, "error": "No credentials configured for this run"}
        field = params.get("field_name")
        if not field:
            return {"success": False, "error": "fill_credential requires field_name"}
        value = credentials.get(field)
        if value is None:
            return {
                "success": False,
                "error": f"Unknown credential field '{field}'. Available: {credentials.field_names()}",
            }
        eid = params.get("element_id")
        if eid:
            elem = next((e for e in current_screen.elements if e.id == eid), None)
            if elem is None:
                return {"success": False, "error": f"Unknown element {eid}"}
            x, y = elem.center
            graph.mark_explored(current_screen.id, eid)
            device.tap(x, y)
            time.sleep(0.5)
        device.type_text(value)
        time.sleep(0.5)
        return {"success": True}

    return {"success": False, "error": f"Unknown tool: {name}"}
