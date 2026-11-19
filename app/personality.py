"""Deterministic disclosed AI character commentary; no model calls."""
from hashlib import sha256

CHARACTER_NAME = "APEX"
DISCLOSURE = "I'm APEX, an AI gaming character."
LINES = {
    "success": ["That finish line never stood a chance!", "Clean run. My circuits are celebrating."],
    "collision": ["That obstacle and I had a disagreement.", "New plan: fewer walls, more wins."],
    "start": ["Let's see what this course has for us.", "Driving lesson begins. Wish my tires luck."],
    "failure": ["That run needs work. Rematch incoming.", "Data collected. Ego slightly bruised."],
}

def comment(event: str, context: str = "") -> dict:
    if event not in LINES:
        raise ValueError("Unsupported event")
    digest = sha256(f"{event}:{context}".encode()).digest()[0]
    return {"character": CHARACTER_NAME, "disclosure": DISCLOSURE,
            "text": LINES[event][digest % len(LINES[event])], "synthetic": True}