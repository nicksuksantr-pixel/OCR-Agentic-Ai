"""Gemini client — the only place that talks to the Gemini API.

Key lives in `.env` (GEMINI_API_KEY) at the project root, never in code or
settings.json. AI Studio key only — no Vertex AI / Service Accounts (rule #2).
The client is created lazily so the whole app keeps working offline.
"""
from pathlib import Path

from src.core.config import paths

ENV_PATH = paths.ENV_PATH  # project root in dev, %LOCALAPPDATA% data dir when installed

# English-only system prompt (CONTEXT language policy). Mirrors the Symbol Tag
# rule: confident symbols become "(name)", unsure ones stay "(unknown symbol)".
BOOST_PROMPT = """You are an OCR engine. Transcribe ALL text visible in this image exactly as written (Thai and English).
Rules:
- Output plain text only, in natural reading order (top-to-bottom, left-to-right). No commentary, no markdown.
- Keep original spelling, numbers, units and punctuation exactly as printed.
- For a technical symbol or graphic you can identify with HIGH confidence, write an English descriptor in parentheses, e.g. (diode), (resistor), (diameter).
- If you are NOT fully sure what a symbol is, write (unknown symbol). Never guess.
- If the image contains no readable text or symbols, output exactly: (nothing readable)
A local OCR engine produced this low-confidence attempt, use it only as a hint and trust your own reading: "{local_text}"
"""


def read_api_key() -> str | None:
    """Read GEMINI_API_KEY from .env (tiny parser — no python-dotenv needed)."""
    if not ENV_PATH.exists():
        return None
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("GEMINI_API_KEY"):
            _, _, value = line.partition("=")
            return value.strip().strip('"').strip("'") or None
    return None


def save_api_key(key: str) -> None:
    """Write/replace GEMINI_API_KEY in .env, preserving any other lines."""
    lines = []
    if ENV_PATH.exists():
        lines = [l for l in ENV_PATH.read_text(encoding="utf-8").splitlines()
                 if not l.strip().startswith("GEMINI_API_KEY")]
    lines.append(f"GEMINI_API_KEY={key.strip()}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def boost_section(crop_path: str, local_text: str, model: str) -> str:
    """Send one queued section crop to Gemini and return its transcription.

    Raises on any failure (no key, network down, quota) — the caller decides
    whether to retry, requeue or stop the run.
    """
    from google import genai  # imported here so offline startup never touches the SDK
    from google.genai import types

    key = read_api_key()
    if not key:
        raise RuntimeError("No GEMINI_API_KEY in .env — set it in Settings.")

    image_bytes = Path(crop_path).read_bytes()
    # Bounded request timeout (ms). Without it a connection that opens then stalls
    # — common on a flaky marine/mobile link — never raises, so the boost drain
    # blocks forever holding _DRAIN_LOCK and bricks every later boost run until the
    # app restarts. A timeout turns that into the normal requeue-and-stop path
    # (audit P2). Generous (2 min) so a slow upload is not a false failure.
    client = genai.Client(api_key=key,
                          http_options=types.HttpOptions(timeout=120_000))
    response = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            BOOST_PROMPT.format(local_text=(local_text or "")[:500]),
        ],
    )
    return (response.text or "").strip()
