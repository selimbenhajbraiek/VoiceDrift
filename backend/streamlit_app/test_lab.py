"""Test lab: run every VoiceDrift module on one recording and see each result. Nothing is saved.

Opened from the sidebar of the main app (streamlit run backend/streamlit_app/app.py).
"""
import os
import sys
import time

import plotly.graph_objects as go
import streamlit as st
import torch

from voice_checker import config
from voice_checker import storage
from backend.streamlit_app import widgets
from voice_checker.audio.quality import QualityError, check_quality, load_audio
from voice_checker.features import embedding, pauses, pitch, transcript
from voice_checker.texts import TEXTS

SAMPLES = {  # synthetic voices reading "The river market" (they say "gray" where the text says "bushy")
    "Sample A · voice 1": config.ROOT / "samples" / "sample_a.wav",
    "Sample B · voice 2": config.ROOT / "samples" / "sample_b.wav",
}
SAMPLE_TEXT = "market"
SPEECH_COLOR, PAUSE_COLOR = "#2a78d6", "#eb6834"


def sample_clips():
    """The built-in samples plus any test-bench clips made by experiments.py."""
    clips = dict(SAMPLES)
    for path in sorted((config.ROOT / "data" / "experiments").glob("*/*.wav")):
        clips[f"Test bench · {path.parent.name} · {path.stem}"] = path
    return clips


def rewind(clip):
    """Uploaded files are read once per step, so jump back to the start before each read."""
    if hasattr(clip, "seek"):
        clip.seek(0)
    return clip


def timed(fn, *args):
    """Run fn(*args) and return (result, error message or None, seconds)."""
    start = time.perf_counter()
    try:
        return fn(*args), None, time.perf_counter() - start
    except QualityError as e:
        return None, str(e), time.perf_counter() - start
    except Exception as e:  # the lab reports any failure instead of crashing
        return None, f"{type(e).__name__}: {e}", time.perf_counter() - start


def system_check():
    """Versions, which models are downloaded, Claude key and stored users."""
    ecapa = (config.MODELS_DIR / "ecapa" / "embedding_model.ckpt").exists()
    whisper = any((config.MODELS_DIR / "whisper").rglob("model.bin"))
    rows = [
        ("Python / PyTorch", f"{sys.version.split()[0]} / {torch.__version__}"),
        ("Voice signature model (ECAPA)", "✅ downloaded" if ecapa else "⬇️ downloads on first run (~80 MB)"),
        ("Speech-to-text model (Whisper base.en)", "✅ downloaded" if whisper else "⬇️ downloads on first run (~140 MB)"),
        ("Claude summaries", "✅ API key set" if os.environ.get("ANTHROPIC_API_KEY") else "⚪ no API key, template summaries"),
        ("Stored users", ", ".join(storage.list_users()) if config.USERS_DIR.exists() else "none yet"),
    ]
    st.markdown("| Check | Status |\n| --- | --- |\n" + "\n".join(f"| {a} | {b} |" for a, b in rows))
    if st.button("Warm up models", help="Loads all models now so the first analysis is fast."):
        loaders = [("VAD", pauses.get_vad), ("ECAPA", embedding.get_model), ("Whisper", transcript.get_model)]
        with st.spinner("Loading models… the first time this downloads them."):
            times = [(name, timed(load)) for name, load in loaders]
        for name, (_, err, sec) in times:
            st.write(f"{'✅' if err is None else '❌'} {name} · {sec:.1f} s" + (f" · {err}" if err else ""))


def choose_recording():
    """Pick the main recording, its text, and an optional second clip to compare voices."""
    samples = sample_clips()
    source = st.radio("Audio source", ["Built-in sample", "Record", "Upload a file"], horizontal=True)
    if source == "Built-in sample":
        clip = samples[st.selectbox("Sample", list(samples))]
        st.audio(str(clip))
        st.caption(f"All samples read “{TEXTS[SAMPLE_TEXT]['title']}” in a synthetic voice. Samples A and B "
                   "say “gray” where the text says “bushy”, so you'll see one misread word. "
                   "Run python -m voice_checker.experiments to add test-bench clips here.")
        text_id = SAMPLE_TEXT
    else:
        text_id = st.selectbox("Text being read", list(TEXTS), format_func=lambda t: TEXTS[t]["title"])
        st.markdown(f"<div class='reading'>{TEXTS[text_id]['text']}</div>", unsafe_allow_html=True)
        if source == "Record":
            clip = st.audio_input("Record yourself reading the text")
        else:
            clip = st.file_uploader("Audio file", type=["wav", "flac", "ogg", "mp3"])

    other = None
    if st.toggle("Also compare the voice with a second recording"):
        pick = st.selectbox("Second recording", [*samples, "Upload a file"])
        other = samples.get(pick) or st.file_uploader("Second audio file", type=["wav", "flac", "ogg", "mp3"], key="other")
    return clip, text_id, other


def run_lab(clip, text_id, other):
    """Run the quality check and every biomarker module; returns {step: (result, error, seconds)}."""
    res = {}
    with st.status("Running every module…", expanded=True) as status:
        st.write("Quality check")
        res["quality"] = timed(check_quality, rewind(clip))
        if res["quality"][1] is None:
            wav = res["quality"][0][0]
        else:  # rejected: run the modules on the raw audio anyway, to see why
            wav, err, _ = timed(load_audio, rewind(clip))
            if err:
                status.update(label="Couldn't read the audio", state="error")
                return res
        steps = [
            ("segments", "Speech segments (silero-vad)", pauses.speech_segments, (wav,)),
            ("pauses", "Pauses", pauses.pause_features, (wav,)),
            ("pitch", "Pitch (Praat)", pitch.pitch_features, (wav,)),
            ("transcript", "Transcript (Whisper)", transcript.transcript_features, (wav, TEXTS[text_id]["text"])),
            ("embedding", "Voice signature (ECAPA)", embedding.embed, (wav,)),
        ]
        for key, label, fn, args in steps:
            st.write(label)
            res[key] = timed(fn, *args)
        if other is not None:
            st.write("Second recording's voice signature")
            res["other"] = timed(lambda c: embedding.embed(load_audio(c)), rewind(other))
        failed = [k for k, v in res.items() if v[1] is not None]
        status.update(label="Done" if not failed else f"Done, with problems in: {', '.join(failed)}",
                      state="complete" if not failed else "error", expanded=False)
    return res


def step_header(title, result):
    """'✅ Title · 1.2 s', plus the error if the step failed. Returns True on success."""
    _, err, sec = result
    st.markdown(f"#### {'✅' if err is None else '❌'} {title} <small>· {sec:.1f} s</small>", unsafe_allow_html=True)
    if err:
        st.error(err)
    return err is None


def timeline_chart(segments):
    """Speech segments and the pauses counted between them, on one time axis."""
    gaps = [(a[1], b[0]) for a, b in zip(segments, segments[1:]) if b[0] - a[1] >= config.MIN_PAUSE_S]
    fig = go.Figure()
    for name, spans, color in [("Speech", segments, SPEECH_COLOR), (f"Pause ≥ {config.MIN_PAUSE_S:g} s", gaps, PAUSE_COLOR)]:
        fig.add_trace(go.Bar(
            y=["Reading"] * len(spans), x=[e - s for s, e in spans], base=[s for s, _ in spans],
            orientation="h", name=name, marker=dict(color=color), width=0.5,
            hovertemplate="%{base:.2f} s, lasts %{x:.2f} s<extra>" + name + "</extra>",
        ))
    fig.update_layout(height=150, barmode="overlay", margin=dict(l=10, r=10, t=10, b=10),
                      legend=dict(orientation="h", y=1.1, yanchor="bottom", x=0))
    fig.update_xaxes(title="seconds", showgrid=False)
    fig.update_yaxes(showticklabels=False)
    return fig


def show_results(res, text_id):
    """One block per module, with its numbers and a pass/fail mark."""
    if step_header("Quality check", res["quality"]):
        q = res["quality"][0][1]
        c1, c2, c3 = st.columns(3)
        c1.metric("Speech length", f"{q['duration_s']:.1f} s", help=f"Needs ≥ {config.MIN_DURATION_S:g} s")
        c2.metric("Voice above background", "n/a" if q["snr_db"] is None else f"{q['snr_db']:.0f} dB",
                  help=f"Needs ≥ {config.MIN_SNR_DB:g} dB")
        c3.metric("Clipped samples", f"{q['clipped_pct']:.2f} %", help=f"Needs ≤ {config.MAX_CLIP_FRACTION:.1%}")
    else:
        st.caption("The app would reject this clip. The modules below ran on the raw audio so you can see why.")
    if "segments" not in res:
        return

    if step_header("Pauses", res["pauses"]):
        p = res["pauses"][0]
        c1, c2 = st.columns(2)
        c1.metric("Pauses", p["pause_count"], help=f"Gaps of {config.MIN_PAUSE_S:g} s or more")
        c2.metric("Pause time", f"{p['pause_ratio']:.0%}", help="Share of the reading spent pausing")
        if res["segments"][1] is None and res["segments"][0]:
            st.plotly_chart(timeline_chart(res["segments"][0]), config={"displayModeBar": False},
                            alt="Timeline of speech segments and the pauses between them.")

    if step_header("Pitch", res["pitch"]):
        f = res["pitch"][0]
        c1, c2 = st.columns(2)
        c1.metric("Average pitch", f"{f['f0_mean_hz']:.0f} Hz")
        c2.metric("Pitch variability", f"{f['f0_std_st']:.1f} semitones")

    if step_header("Transcript", res["transcript"]):
        t = res["transcript"][0]
        c1, c2, c3 = st.columns(3)
        c1.metric("Speaking rate", f"{t['wpm']:.0f} wpm")
        c2.metric("Reading errors", f"{t['wer']:.0%}", help="Word error rate vs. the expected text")
        c3.metric("Filler words", t["filler_count"])
        st.markdown("What we heard · " + widgets.DIFF_LEGEND, unsafe_allow_html=True)
        st.markdown(widgets.transcript_html(TEXTS[text_id]["text"], t["transcript"]), unsafe_allow_html=True)

    if step_header("Voice signature", res["embedding"]):
        vec = res["embedding"][0]
        c1, c2, c3 = st.columns(3)
        c1.metric("Dimensions", len(vec))
        c2.metric("Vector length", f"{float((vec ** 2).sum() ** 0.5):.3f}", help="L2-normalized, so 1.000")
        if "other" in res and res["other"][1] is None:
            c3.metric("Similarity to 2nd clip", f"{float(vec @ res['other'][0]):.2f}",
                      help="Cosine similarity, 1 = identical. In our tests: same voice 0.98, different voice 0.31.")
        elif "other" in res:
            st.error(f"Second recording: {res['other'][1]}")


st.title("🧪 Test lab")
st.caption("Check every part of VoiceDrift on one recording and see what each module measures. Nothing is saved.")
st.sidebar.caption("Research prototype, not a medical device. Audio is processed locally.")

st.subheader("1 · System check")
system_check()

st.subheader("2 · Choose a recording")
clip, text_id, other = choose_recording()
if st.button("Run all checks", type="primary", disabled=clip is None):
    st.session_state.lab = (run_lab(clip, text_id, other), text_id)

if "lab" in st.session_state:
    st.subheader("3 · Results")
    show_results(*st.session_state.lab)
