"""Central settings for VoiceDrift: models, thresholds, z-score floors and paths."""
from pathlib import Path

# --- Models -----------------------------------------------------------------
ECAPA_MODEL = "speechbrain/spkrec-ecapa-voxceleb"  # 192-dim speaker embedding
WHISPER_MODEL = "base.en"
WHISPER_COMPUTE = "int8"
CLAUDE_MODEL = "claude-opus-5-5"

# --- Audio quality check ----------------------------------------------------
SAMPLE_RATE = 16_000
MIN_DURATION_S = 8.0       # reject clips shorter than this
CLIP_LEVEL = 0.98          # |sample| at or above this counts as clipped
MAX_CLIP_FRACTION = 0.001  # reject if more than 0.1 % of samples are clipped
MIN_SNR_DB = 10.0          # reject if speech is less than 10 dB above the background
MIN_NOISE_S = 0.3          # need this much non-speech audio to estimate the background
SPEECH_MARGIN_S = 0.2      # audio kept around the first/last speech for analysis

# --- Biomarker extraction ---------------------------------------------------
VAD_THRESHOLD = 0.5        # silero-vad speech probability threshold
MIN_PAUSE_S = 0.25         # gaps at least this long count as pauses
PITCH_FLOOR_HZ = 75
PITCH_CEILING_HZ = 500
FILLER_WORDS = {"um", "umm", "uh", "uhh", "er", "erm", "ah", "ahh"}
# Whisper tends to drop disfluencies; a prompt that contains some makes it keep them.
FILLER_PROMPT = "Um, so, uh, I was reading, er, the text. Ah, okay."

# --- Drift scoring ----------------------------------------------------------
BASELINE_N = 3             # first N readings of a text form that text's baseline
EMBEDDING_STD_FLOOR = 0.01
# Minimum baseline std per biomarker, roughly the normal day-to-day variation of
# a healthy reader, so three near-identical baseline readings can't blow up z.
STD_FLOORS = {
    "wpm": 8.0,            # words per minute
    "wer": 0.03,           # 3 percentage points of word error rate
    "filler_count": 1.5,
    "f0_mean_hz": 8.0,
    "f0_std_st": 0.4,      # semitones
    "pause_count": 2.0,
    "pause_ratio": 0.03,
}
WATCH_INDEX = 2.0          # Stable < 2 <= Watch < 3.5 <= Changed
CHANGED_INDEX = 3.5
PERSIST_K = 3              # alert when the last K scored readings are Watch or worse
NOTABLE_Z = 1.5            # |z| from which a biomarker is mentioned in the summary

# Display name and unit of every score (scalars plus the embedding).
LABELS = {
    "embedding": ("Voice signature", "z"),
    "wpm": ("Speaking rate", "words/min"),
    "wer": ("Reading errors", "WER"),
    "filler_count": ("Filler words", "count"),
    "f0_mean_hz": ("Average pitch", "Hz"),
    "f0_std_st": ("Pitch variability", "semitones"),
    "pause_count": ("Pauses", "count"),
    "pause_ratio": ("Pause time", "share"),
}

# --- Paths ------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
USERS_DIR = ROOT / "data" / "users"   # one JSON per user
MODELS_DIR = ROOT / "models"          # downloaded model weights

DEMO_USER = "Demo User"
