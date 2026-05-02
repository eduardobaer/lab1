import networkx as nx

from spider.screen import phash_distance


class ScreenGraph:
    def __init__(self, phash_threshold: int = 5):
        self.g: nx.MultiDiGraph = nx.MultiDiGraph()
        self.phash_threshold = phash_threshold
        self.screens_done: set[str] = set()
        # (screen_id, element_id) -> explored?
        self.element_explored: dict[tuple[str, str], bool] = {}
        # screen_id -> recorded element ids (the union seen across visits)
        self.screen_elements: dict[str, set[str]] = {}

    def find_existing_screen(self, new_screen) -> str | None:
        """Look up an existing canonical screen ID by structural hash, or by
        perceptual hash + matching activity (handles minor render variations)."""
        for sid, data in self.g.nodes(data=True):
            if data.get("structural_hash") == new_screen.structural_hash:
                return sid
            existing_phash = data.get("phash")
            if existing_phash and phash_distance(existing_phash, new_screen.phash) <= self.phash_threshold:
                if data.get("activity") == new_screen.activity:
                    return sid
        return None

    def observe(self, screen) -> tuple[str, bool]:
        """Register screen if new; return (canonical_id, is_new)."""
        existing = self.find_existing_screen(screen)
        if existing:
            # Refresh element set with anything new we saw this visit
            existing_elems = self.screen_elements.setdefault(existing, set())
            for e in screen.elements:
                if e.id not in existing_elems:
                    existing_elems.add(e.id)
                    if e.clickable or e.long_clickable:
                        self.element_explored.setdefault((existing, e.id), False)
            return existing, False

        self.g.add_node(
            screen.id,
            phash=screen.phash,
            structural_hash=screen.structural_hash,
            package=screen.package,
            activity=screen.activity,
            screenshot=str(screen.screenshot_path),
        )
        self.screen_elements[screen.id] = {e.id for e in screen.elements}
        for e in screen.elements:
            if e.clickable or e.long_clickable:
                self.element_explored[(screen.id, e.id)] = False
        return screen.id, True

    def add_transition(self, from_id: str, to_id: str, action_name: str, element_id: str | None = None) -> None:
        self.g.add_edge(from_id, to_id, action=action_name, element=element_id)

    def mark_explored(self, screen_id: str, element_id: str) -> None:
        self.element_explored[(screen_id, element_id)] = True

    def mark_screen_done(self, screen_id: str) -> None:
        self.screens_done.add(screen_id)
        for (sid, eid) in list(self.element_explored.keys()):
            if sid == screen_id:
                self.element_explored[(sid, eid)] = True

    def unexplored_count(self, screen_id: str) -> int:
        if screen_id in self.screens_done:
            return 0
        return sum(
            1 for (sid, eid), v in self.element_explored.items() if sid == screen_id and not v
        )

    def is_complete(self) -> bool:
        if not self.g.nodes:
            return False
        return all(self.unexplored_count(sid) == 0 for sid in self.g.nodes)

    def summarize(self, current_screen_id: str | None = None, max_screens: int = 30) -> str:
        lines = [
            f"Screens visited: {len(self.g.nodes)}, transitions: {self.g.number_of_edges()}"
        ]
        for sid, data in list(self.g.nodes(data=True))[:max_screens]:
            marker = "→" if sid == current_screen_id else " "
            unexplored = self.unexplored_count(sid)
            if sid in self.screens_done:
                status = "✓"
            elif unexplored == 0:
                status = "·"
            else:
                status = f"{unexplored}u"
            activity = (data.get("activity") or "?").split(".")[-1] or "?"
            lines.append(f"  {marker} {sid} ({activity}) [{status}]")
        if len(self.g.nodes) > max_screens:
            lines.append(f"  … and {len(self.g.nodes) - max_screens} more")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "nodes": [{"id": n, **d} for n, d in self.g.nodes(data=True)],
            "edges": [{"from": u, "to": v, **d} for u, v, d in self.g.edges(data=True)],
            "screens_done": list(self.screens_done),
            "elements_explored": [
                {"screen_id": sid, "element_id": eid, "explored": v}
                for (sid, eid), v in self.element_explored.items()
            ],
        }
