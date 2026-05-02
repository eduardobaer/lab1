import re
from dataclasses import dataclass

from lxml import etree

BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


@dataclass
class Element:
    id: str
    class_name: str
    resource_id: str
    text: str
    content_desc: str
    bounds: tuple[int, int, int, int]
    clickable: bool
    long_clickable: bool
    scrollable: bool
    focusable: bool
    enabled: bool

    @property
    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "class": self.class_name,
            "resource_id": self.resource_id,
            "text": self.text,
            "content_desc": self.content_desc,
            "bounds": list(self.bounds),
            "clickable": self.clickable,
            "long_clickable": self.long_clickable,
            "scrollable": self.scrollable,
        }

    def label(self) -> str:
        parts = [self.class_name.split(".")[-1]]
        if self.text:
            parts.append(f'text="{self.text[:60]}"')
        if self.content_desc:
            parts.append(f'desc="{self.content_desc[:60]}"')
        if self.resource_id:
            parts.append(f'id="{self.resource_id.split("/")[-1]}"')
        return " ".join(parts)


def parse_hierarchy(xml_text: str) -> list[Element]:
    """Extract interactive / labeled elements from a uiautomator XML dump."""
    try:
        root = etree.fromstring(xml_text.encode())
    except etree.XMLSyntaxError:
        return []

    elements: list[Element] = []
    counter = 0
    for node in root.iter():
        if node.tag != "node":
            continue
        attrs = node.attrib
        clickable = attrs.get("clickable") == "true"
        long_clickable = attrs.get("long-clickable") == "true"
        scrollable = attrs.get("scrollable") == "true"
        focusable = attrs.get("focusable") == "true"
        text = attrs.get("text", "")
        content_desc = attrs.get("content-desc", "")

        # Keep anything interactive or that has user-visible text/desc
        if not (clickable or long_clickable or scrollable or focusable or text or content_desc):
            continue

        bounds_m = BOUNDS_RE.match(attrs.get("bounds", ""))
        if not bounds_m:
            continue
        bounds = tuple(int(v) for v in bounds_m.groups())
        if bounds[2] - bounds[0] <= 0 or bounds[3] - bounds[1] <= 0:
            continue

        elements.append(
            Element(
                id=f"e_{counter}",
                class_name=attrs.get("class", ""),
                resource_id=attrs.get("resource-id", ""),
                text=text,
                content_desc=content_desc,
                bounds=bounds,
                clickable=clickable,
                long_clickable=long_clickable,
                scrollable=scrollable,
                focusable=focusable,
                enabled=attrs.get("enabled") == "true",
            )
        )
        counter += 1
    return elements
