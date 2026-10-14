"""Optional AI briefing written by Claude from the Dashboard's numbers.

Off unless ANTHROPIC_API_KEY is set in backend\\.env. The rule-based briefing (insights.py)
always works without it. Claude only sees the computed summary (numbers, titles, trend names),
never API tokens, and is told to use nothing but those numbers, so it rewrites and prioritises
rather than inventing facts.

Results are cached per workspace until the underlying numbers change.
"""
import hashlib
import json

import config

SYSTEM = """You are a social media strategist writing a short briefing for a busy owner or editor.
You receive a JSON summary computed from their own accounts, their competitors' accounts and internet trends.

Rules:
- Use ONLY facts and numbers present in the JSON. Never invent numbers, posts, competitors or trends.
- Plain, friendly English a non-marketer understands. No jargon, no hype, no emojis.
- Be specific: name the platform, topic, competitor or trend each point is about.
- Respect the brand_safety setting: "strict" means never suggest content tied to sensitive news
  (death, disasters, violence, politics, religion); "standard" means only with care and expertise;
  "newsroom" means cover it responsibly with verification.
- Suggestions must be original content ideas, never copying a competitor.
- If the data is thin, say so in the summary instead of guessing."""

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "3-4 sentences: what's going on and the single most important thing to do."},
        "priorities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "why": {"type": "string", "description": "The evidence from the JSON, with its numbers."},
                    "action": {"type": "string", "description": "One concrete thing to do this week."},
                },
                "required": ["title", "why", "action"],
                "additionalProperties": False,
            },
        },
        "content_ideas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "idea": {"type": "string"},
                    "based_on": {"type": "string", "description": "Which trend, topic or finding it comes from."},
                    "format": {"type": "string"},
                    "caution": {"type": "string", "description": "Brand-safety note, or empty."},
                },
                "required": ["idea", "based_on", "format", "caution"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "priorities", "content_ideas"],
    "additionalProperties": False,
}

_cache = {}  # (org_id, digest) -> result


def configured():
    return bool(config.ANTHROPIC_API_KEY)


def _digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def briefing(org_id, data):
    """{"summary", "priorities", "content_ideas", "model", "cached"}. Raises ValueError with a readable message."""
    if not configured():
        raise ValueError("AI briefing is off. Add ANTHROPIC_API_KEY to backend\\.env to turn it on.")
    key = (org_id, _digest(data))
    if key in _cache:
        return {**_cache[key], "cached": True}
    try:
        import anthropic
    except ImportError as exc:
        raise ValueError("The anthropic package isn't installed. Run: env\\Scripts\\pip install -r requirements.txt") from exc

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=90.0)
    try:
        response = client.messages.create(
            model=config.AI_MODEL,
            max_tokens=4000,
            system=SYSTEM,
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": "Write the briefing from this data:\n" + json.dumps(data, ensure_ascii=False, default=str)}],
            # If a safety classifier declines, let the API retry on its recommended fallback model.
            extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
            extra_body={"fallbacks": "default"},
        )
    except anthropic.AuthenticationError as exc:
        raise ValueError("The Anthropic API key is invalid. Check ANTHROPIC_API_KEY in backend\\.env.") from exc
    except anthropic.RateLimitError as exc:
        raise ValueError("The AI service is busy (rate limit). Try again in a minute.") from exc
    except anthropic.APIStatusError as exc:
        raise ValueError(f"The AI service returned an error ({exc.status_code}).") from exc
    except anthropic.APIConnectionError as exc:
        raise ValueError("Can't reach the AI service. Check the internet connection.") from exc

    if response.stop_reason == "refusal":
        raise ValueError("The AI declined to write this briefing. The rule-based briefing above is still accurate.")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("The AI returned an incomplete answer. Try again.") from exc
    result["model"] = response.model
    _cache[key] = result
    return {**result, "cached": False}
