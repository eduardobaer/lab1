import base64
import json
from io import BytesIO

from PIL import Image
from anthropic import Anthropic

from spider.credentials import Credentials
from spider.prompts import (
    PRD_SYSTEM_PROMPT,
    build_system_prompt,
    build_tools,
    step_user_message,
)


def downsample_image(png_bytes: bytes, max_dim: int = 1080, quality: int = 85) -> str:
    """Resize a screenshot to bound the long edge, JPEG-encode, return base64."""
    img = Image.open(BytesIO(png_bytes)).convert("RGB")
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()


class LLM:
    def __init__(
        self,
        model: str = "claude-opus-4-7",
        image_max_dim: int = 1080,
        credentials: Credentials | None = None,
    ):
        self.client = Anthropic()  # picks up ANTHROPIC_API_KEY from env
        self.model = model
        self.image_max_dim = image_max_dim
        # Pre-render the system prompt + tools once. Both fold the credential
        # field NAMES (never values) into Claude's view of the world.
        field_names = credentials.field_names() if credentials else []
        self._system_prompt = build_system_prompt(field_names)
        self._tools = build_tools(field_names)

    def _supports_max_effort(self) -> bool:
        # max effort is Opus-tier only (Opus 4.6 and later).
        return self.model.startswith("claude-opus-4-")

    def choose_action(
        self,
        *,
        screenshot_png: bytes,
        elements_text: str,
        graph_summary: str,
        history_text: str,
        observations_summary: str,
        activity: str,
        package: str,
        current_screen_id: str,
    ) -> tuple[str, dict, str, dict]:
        """Returns (tool_name, tool_input, reasoning_text, usage_dict)."""
        b64 = downsample_image(screenshot_png, self.image_max_dim)
        user_content = step_user_message(
            screenshot_b64=b64,
            elements_text=elements_text,
            graph_summary=graph_summary,
            history_text=history_text,
            observations_summary=observations_summary,
            activity=activity,
            package=package,
            current_screen_id=current_screen_id,
        )

        # Cache the system prompt + tool definitions (rendered in order: tools → system → messages).
        # A breakpoint on the last system block caches both.
        system = [
            {
                "type": "text",
                "text": self._system_prompt,
                "cache_control": {"type": "ephemeral"},
            },
        ]

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=system,
            tools=self._tools,
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": user_content}],
        )

        reasoning = ""
        tool_name: str | None = None
        tool_input: dict = {}
        for block in response.content:
            if block.type == "text":
                reasoning += block.text
            elif block.type == "tool_use":
                tool_name = block.name
                tool_input = dict(block.input) if isinstance(block.input, dict) else {}
                break  # we execute exactly one tool per turn

        if tool_name is None:
            # No tool call — recover by waiting briefly and re-prompting next turn.
            tool_name = "wait"
            tool_input = {"seconds": 1}

        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_creation_input_tokens": getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
            "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0) or 0,
        }

        return tool_name, tool_input, reasoning, usage

    def synthesize_prd(self, graph_data: dict, observations: dict, app_meta: dict) -> str:
        """Generate the final PRD as Markdown. Streams the response."""
        # Truncate the graph/observations payloads if absurdly large, to stay
        # within reasonable input cost. 1M context can hold a lot, but the PRD
        # quality is bounded by relevance, not raw bytes.
        graph_json = json.dumps(graph_data, indent=2, default=str)
        if len(graph_json) > 200_000:
            graph_json = graph_json[:200_000] + "\n... (truncated)"
        obs_json = json.dumps(observations, indent=2, default=str)
        if len(obs_json) > 100_000:
            obs_json = obs_json[:100_000] + "\n... (truncated)"

        prompt = (
            f"# App metadata\n```json\n{json.dumps(app_meta, indent=2, default=str)}\n```\n\n"
            f"# State graph\n```json\n{graph_json}\n```\n\n"
            f"# Observations\n```json\n{obs_json}\n```\n\n"
            "Now produce the comprehensive PRD as instructed in the system prompt. "
            "Markdown only, no preamble."
        )

        kwargs = dict(
            model=self.model,
            max_tokens=64000,
            thinking={"type": "adaptive"},
            system=PRD_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        if self._supports_max_effort():
            kwargs["output_config"] = {"effort": "max"}

        with self.client.messages.stream(**kwargs) as stream:
            final = stream.get_final_message()

        out_parts = [b.text for b in final.content if b.type == "text"]
        return "\n".join(out_parts)
