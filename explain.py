"""Plain-language summaries of what changed: templates, or optionally Claude's wording.

Nothing here diagnoses: summaries only describe changes and, when they persist,
suggest rest or checking in with a professional.
"""
import os

import anthropic

import config
import drift

MEANING = {  # what each biomarker measures, for the results table
    "embedding": "How much your overall voice sounds like your baseline recordings",
    "wpm": "How many words you read per minute",
    "wer": "Share of words misread, skipped or added",
    "filler_count": "How often you said um, uh, er or ah",
    "f0_mean_hz": "How high or low your voice is on average",
    "f0_std_st": "How much your pitch rises and falls (melody)",
    "pause_count": "How often you stopped for a quarter second or more",
    "pause_ratio": "Share of the reading spent in pauses",
}

PHRASES = {  # biomarker: (phrase when higher than usual, phrase when lower)
    "embedding": ("your voice sounded less like your usual recordings", None),
    "wpm": ("you read faster than usual", "you read more slowly than usual"),
    "wer": ("you misread or skipped more words than usual", "you made fewer reading slips than usual"),
    "filler_count": ("you used more filler words than usual", "you used fewer filler words than usual"),
    "f0_mean_hz": ("your voice was higher-pitched than usual", "your voice was lower-pitched than usual"),
    "f0_std_st": ("your intonation was more varied than usual", "your voice sounded flatter than usual"),
    "pause_count": ("you paused more often than usual", "you paused less often than usual"),
    "pause_ratio": ("you spent more of the reading pausing", "you spent less of the reading pausing"),
}

STATUS_LINES = {
    "Stable": "Overall, this reading is within your normal range.",
    "Watch": "This is a small shift worth keeping an eye on.",
    "Changed": "This is a clear change from how you usually read this text.",
}

EVERYDAY = (
    "Everyday things such as tiredness, a different room or microphone, or reading "
    "at another time of day can cause this."
)

SYSTEM_PROMPT = """You write short, friendly feedback for VoiceDrift, a research prototype that compares a person's read-aloud recording with their own earlier recordings of the same text.

Rules:
- Write exactly two sentences in plain, warm language, speaking to the user as "you".
- Describe only what changed (for example slower reading or more pauses) and how clearly. Do not quote numbers or statistics.
- Never diagnose, and never name, suggest or speculate about any medical condition, illness or cause. The app is not a medical device.
- If the status is Watch or Changed, say that everyday things like tiredness or a different microphone can affect a reading, and suggest resting or checking in with a healthcare professional if the changes persist.
- If the status is Stable, reassure the user briefly."""


def describe(key, z):
    """Plain-language direction of one change, e.g. 'you read more slowly than usual'."""
    up, down = PHRASES[key]
    return up if z > 0 or down is None else down


def notable_changes(zs, n=3):
    """The top n changes as (key, z), keeping only those with |z| >= NOTABLE_Z."""
    return [(k, z) for k, z in drift.top_changes(zs, n) if abs(z) >= config.NOTABLE_Z]


def join_phrases(phrases):
    """['a', 'b', 'c'] -> 'a, b and c'."""
    return phrases[0] if len(phrases) == 1 else ", ".join(phrases[:-1]) + " and " + phrases[-1]


def template_summary(zs, status, persistent=False):
    """A short summary built from the top 2-3 z-scores."""
    changes = notable_changes(zs)
    if not changes:
        return "This reading was close to your usual baseline; nothing stood out."
    text = f"Compared with your baseline, {join_phrases([describe(k, z) for k, z in changes])}. "
    text += STATUS_LINES[status]
    if status != "Stable":
        text += " " + EVERYDAY
        if persistent:
            text += (" Because it has now shown up in several readings in a row, consider "
                     "resting and checking in with a healthcare professional.")
        else:
            text += (" If changes like this keep showing up over several readings, consider "
                     "resting and checking in with a healthcare professional.")
    return text


def facts_for_claude(zs, status, persistent):
    """The numbers Claude sees: status and top changes only (no audio, no transcript, no name)."""
    lines = [
        f"Status: {status} (Stable < {config.WATCH_INDEX}, Watch, Changed >= {config.CHANGED_INDEX})",
        f"Watch or worse in the last {config.PERSIST_K} readings in a row: {'yes' if persistent else 'no'}",
        "Biggest changes vs. the user's baseline (z-score = how unusual, 2+ is notable):",
    ]
    for key, z in drift.top_changes(zs):
        lines.append(f"- {config.LABELS[key][0]}: {describe(key, z)} (z = {z:+.1f})")
    return "\n".join(lines)


def claude_summary(zs, status, persistent=False):
    """A friendlier 2-sentence summary from Claude, or None without an API key or on any failure."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    client = anthropic.Anthropic(timeout=30.0, max_retries=1)
    try:
        response = client.beta.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2000,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # retry on another model if a safety filter declines
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": facts_for_claude(zs, status, persistent)}],
        )
    except anthropic.APIError:
        return None  # network, auth, rate limit or server error: use the template
    if response.stop_reason != "end_turn":  # refusal or truncated
        return None
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return text or None


def summarize(zs, status, persistent=False, use_claude=True):
    """Return (summary, source) where source is "claude" or "template"."""
    text = claude_summary(zs, status, persistent) if use_claude else None
    if text:
        return text, "claude"
    return template_summary(zs, status, persistent), "template"
