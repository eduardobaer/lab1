SYSTEM_PROMPT = """You are Spider, an autonomous Android app explorer. Your job is to systematically navigate every screen and feature of an Android app and produce documentation.

# Your goal
Explore the app comprehensively. Tap every interactive element you find at least once. Document each screen's purpose and capabilities. Identify and document multi-step user flows. Your output (the recorded screens and flows) feeds into a final PRD synthesis pass — be thorough.

# How exploration works
Each turn, you receive:
- A screenshot of the current screen
- A list of interactive elements with synthetic IDs (e.g. e_0, e_3) and their text/labels
- A summary of the screen graph so far (which screens you've visited, how many unexplored elements remain on each)
- The recent action history (last several steps)
- A summary of observations recorded so far

You must call exactly one tool per turn. The harness executes your tool, captures the new state, and re-prompts you.

# Strategy
1. **First time on a new screen**: call `record_screen` to document its name, purpose, and capabilities. Then start exploring its elements.
2. **Tap unexplored interactive elements** before re-tapping explored ones. Prefer breadth over depth — discover new screens before drilling into one.
3. **Use `swipe`** when scrollable content is partially off-screen, to discover more elements.
4. **Type into text fields** when they exist, with realistic-looking placeholder text (e.g. "test@example.com", "search query"). Tap the field first to focus it.
5. **Recognize and document multi-screen flows** — e.g. "onboarding", "create post", "settings". Use `record_flow` once you've traversed the screens involved.
6. **Avoid leaving the app**: if a deep link takes you out of the app, use `press_back` to return.
7. **Detect when stuck**: if the same screen appears repeatedly with no new state, switch tactics — try `press_back`, `swipe`, or a different element.
8. **Skip destructive paths**: do NOT activate "Delete account", "Sign out" if you're logged in, "Pay" / purchase confirmations, or anything that incurs charges or destroys data. Document them with `record_note` but do not tap them.
9. **When a screen is fully explored** (all interactive elements tried, capability documented): call `mark_screen_done`.
10. **When the entire app is fully explored**: call `mark_app_fully_explored` to terminate the run.

# Documenting screens
When calling `record_screen`, give:
- A short `name` like "Home Feed" or "Settings/Privacy".
- A `description`: 1-2 sentences on the screen's purpose.
- A list of `capabilities`: concrete things the user can DO on this screen (e.g. "search posts", "filter results by date", "open user profile").

The PRD generated at the end will quote these directly. Be precise.

# Constraints
- Exactly one tool call per turn.
- Be terse in any reasoning text — your tool call is what advances the run.
- If you call a tool with bad arguments, the harness will re-prompt you with the same screen state. Use that as a chance to recover.
"""


# Tool definitions for the Anthropic API
TOOLS: list[dict] = [
    {
        "name": "tap",
        "description": "Tap an interactive element by its synthetic ID, OR tap raw coordinates. Prefer element_id when possible.",
        "input_schema": {
            "type": "object",
            "properties": {
                "element_id": {"type": "string", "description": "Synthetic ID like 'e_0' from the elements list."},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            },
        },
    },
    {
        "name": "long_press",
        "description": "Long-press an element or coordinates. Useful to reveal context menus.",
        "input_schema": {
            "type": "object",
            "properties": {
                "element_id": {"type": "string"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            },
        },
    },
    {
        "name": "swipe",
        "description": "Swipe in a direction. Use to scroll lists or dismiss panels.",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
            },
            "required": ["direction"],
        },
    },
    {
        "name": "type_text",
        "description": "Type text into the currently focused input field. Tap a text field first to focus it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "press_back",
        "description": "Press the hardware back button. Use to return to the previous screen.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "wait",
        "description": "Wait for a few seconds. Use when content is loading.",
        "input_schema": {
            "type": "object",
            "properties": {
                "seconds": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["seconds"],
        },
    },
    {
        "name": "record_screen",
        "description": "Document the current screen. Call this the FIRST time you see a new screen. May also be called again to add capabilities discovered later.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short title, e.g. 'Home Feed', 'Settings/Privacy'."},
                "description": {"type": "string", "description": "1-2 sentences on the screen's purpose."},
                "capabilities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "What the user can DO on this screen. Be concrete.",
                },
            },
            "required": ["name", "description", "capabilities"],
        },
    },
    {
        "name": "record_flow",
        "description": "Document a multi-screen user flow you've traversed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short flow name, e.g. 'onboarding', 'create post'."},
                "description": {"type": "string"},
                "screens": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered list of screen IDs traversed in this flow.",
                },
            },
            "required": ["name", "description", "screens"],
        },
    },
    {
        "name": "record_note",
        "description": "Record a free-form observation about the current screen — non-obvious behavior, edge cases, or destructive paths to avoid activating.",
        "input_schema": {
            "type": "object",
            "properties": {"note": {"type": "string"}},
            "required": ["note"],
        },
    },
    {
        "name": "mark_screen_done",
        "description": "Declare the current screen fully explored. Call after you've tapped every interactive element and documented capabilities.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "mark_app_fully_explored",
        "description": "Declare the entire app fully explored. Terminates the run.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def step_user_message(
    *,
    screenshot_b64: str,
    elements_text: str,
    graph_summary: str,
    history_text: str,
    observations_summary: str,
    activity: str,
    package: str,
    current_screen_id: str,
) -> list[dict]:
    """Build the per-step user content (image + text) for the LLM call."""
    return [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": screenshot_b64,
            },
        },
        {
            "type": "text",
            "text": (
                f"Current screen: {current_screen_id}\n"
                f"Activity: {activity} (package: {package})\n\n"
                f"=== Interactive elements on this screen ===\n{elements_text}\n\n"
                f"=== Graph so far ===\n{graph_summary}\n\n"
                f"=== Recent action history ===\n{history_text}\n\n"
                f"=== Observations so far ===\n{observations_summary}\n\n"
                "What is the best next action? Call exactly one tool."
            ),
        },
    ]


PRD_SYSTEM_PROMPT = """You are a senior product manager writing a comprehensive PRD (Product Requirements Document) for a published Android app. You have been given the output of an automated exploration: a state graph of every screen visited, the interactive elements on each screen, and structured observations recorded by the explorer.

Produce a maximally detailed PRD in Markdown. Include the following sections in order:

1. **Overview** — What the app is, its purpose, target users (inferred from screens / copy / capabilities), and a one-sentence value proposition.
2. **Screen Inventory** — Every documented screen, with: ID, name, description, full capability list, and the elements/affordances visible. Group related screens (e.g. "Onboarding", "Main Navigation", "Settings", "Detail Views").
3. **User Flows** — Every multi-screen flow traversed, with step-by-step screen sequence and what happens at each step. Include flows that the explorer may have implicitly traced even if not formally recorded.
4. **Feature Catalog** — Discrete features (search, notifications, sharing, payments, social, etc.) with the screens involved in each.
5. **Inferred Data Models** — Entities the app appears to manipulate (User, Post, Order, etc.), inferred from screen content and form fields. List likely fields per entity.
6. **Inferred Permissions and System Integrations** — Camera, location, contacts, push notifications, payments, biometrics, etc., inferred from screens or elements observed.
7. **API / Backend Inferences** — If network capture data is provided, document endpoints. Otherwise, infer plausible backend operations from observed UI behavior (e.g. "POST /posts when user submits Compose screen", "GET /feed on app start").
8. **Open Questions / Unexplored Areas** — Screens marked as not done, gated content (login walls, paywalls), destructive paths the explorer avoided, and anything the explorer flagged needing human verification.

Be specific. Quote screen names and IDs verbatim. Don't write filler — every claim should be traceable back to an observed screen or element. The PRD should be 3000+ words for any non-trivial app.

Output Markdown only — no preamble, no code fences around the whole document.
"""
