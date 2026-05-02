from dataclasses import dataclass, field


@dataclass
class ScreenDoc:
    name: str
    description: str
    capabilities: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class FlowDoc:
    name: str
    description: str
    screens: list[str] = field(default_factory=list)


class Observer:
    """Sink for record_* tool calls. The PRD generator reads from here."""

    def __init__(self):
        self.screens: dict[str, ScreenDoc] = {}
        self.flows: dict[str, FlowDoc] = {}

    def record_screen(
        self,
        screen_id: str,
        name: str,
        description: str,
        capabilities: list[str],
    ) -> None:
        if screen_id in self.screens:
            doc = self.screens[screen_id]
            for c in capabilities:
                if c not in doc.capabilities:
                    doc.capabilities.append(c)
            if description and not doc.description:
                doc.description = description
            if name and not doc.name:
                doc.name = name
        else:
            self.screens[screen_id] = ScreenDoc(
                name=name,
                description=description,
                capabilities=list(capabilities),
            )

    def record_flow(self, name: str, description: str, screens: list[str]) -> None:
        if name in self.flows:
            doc = self.flows[name]
            for s in screens:
                if s not in doc.screens:
                    doc.screens.append(s)
            if description:
                doc.description = description
        else:
            self.flows[name] = FlowDoc(
                name=name,
                description=description,
                screens=list(screens),
            )

    def record_note(self, screen_id: str, note: str) -> None:
        doc = self.screens.setdefault(screen_id, ScreenDoc(name="", description=""))
        doc.notes.append(note)

    def summary(self, max_chars: int = 2000) -> str:
        if not self.screens and not self.flows:
            return "(no observations recorded yet)"
        lines = []
        if self.screens:
            lines.append(f"Documented screens ({len(self.screens)}):")
            for sid, doc in list(self.screens.items())[:20]:
                lines.append(f"  {sid}: {doc.name} — {doc.description[:80]}")
        if self.flows:
            lines.append(f"Documented flows ({len(self.flows)}):")
            for name, doc in list(self.flows.items())[:10]:
                lines.append(
                    f"  {name}: {doc.description[:80]} ({len(doc.screens)} screens)"
                )
        return "\n".join(lines)[:max_chars]

    def to_dict(self) -> dict:
        return {
            "screens": {
                sid: {
                    "name": doc.name,
                    "description": doc.description,
                    "capabilities": doc.capabilities,
                    "notes": doc.notes,
                }
                for sid, doc in self.screens.items()
            },
            "flows": {
                name: {
                    "name": doc.name,
                    "description": doc.description,
                    "screens": doc.screens,
                }
                for name, doc in self.flows.items()
            },
        }
