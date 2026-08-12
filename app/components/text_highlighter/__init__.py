"""Text highlighter Streamlit component — returns selected text to Python."""
from pathlib import Path
import streamlit.components.v1 as components

_component = components.declare_component(
    "text_highlighter",
    path=str(Path(__file__).resolve().parent),
)


def text_highlighter(text: str, key: str | None = None) -> str | None:
    """Render selectable output text; returns highlighted snippet or None."""
    return _component(text=text, key=key, default=None)
