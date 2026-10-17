"""Voice check, the home page: compare a reading or an "aaah" with research recordings of voice conditions.

It says which condition a voice is most similar to, never that the person has it. The first page of the
app (streamlit run backend/streamlit_app/app.py).
"""
import html

import streamlit as st

from voice_checker.audio.quality import QualityError
from voice_checker.screening import READING_TASKS, TASKS, describe, predict
from voice_checker.screening.features import VOICE_QUALITY, voice_quality
from voice_checker.texts import TEXTS

AUDIO_TYPES = ["wav", "flac", "ogg", "mp3"]


def show_verdict(task, wav):
    """One headline: a healthy-sounding voice, or the single closest condition."""
    with st.spinner("Comparing with the research recordings…"):
        condition, right = predict.verdict(task, wav)
    headline, detail = describe(condition, right)
    if condition is None:
        st.success(f"### ✅ {headline}")
    else:
        st.error(f"### ⚠️ {headline}")
    st.caption(detail)


def reliability(tasks):
    """How the models did on people they had never heard, tucked away in an expander."""
    with st.expander("How reliable is this?"):
        for task in tasks:
            bundle = predict.load(task)
            some = bundle["speaker_metrics"]
            names = [c for c in (bundle.get("condition_groups") or {}).get("classes", []) if c != "Healthy"]
            st.markdown(f"**{TASKS[task]['title']}:** tested on {bundle['n_groups']} people it had never heard, it "
                        f"flagged {some['sensitivity']:.0%} of people with a voice condition and "
                        f"{1 - some['specificity']:.0%} of healthy people of the same ages and sexes. "
                        + (f"It can only name: {', '.join(names)}." if names else ""))
        for task in READING_TASKS:
            if task in tasks or not TASKS[task].get("disabled"):
                continue
            st.caption(f"🚫 {TASKS[task]['title']} is switched off: {TASKS[task]['disabled']}")


def clean(clip, vowel=False):
    """Quality-check a reading or an "aaah"; returns the cleaned audio, or None after showing the problem."""
    try:
        return predict.prepare(clip, vowel)
    except QualityError as e:
        st.error(f"**Let's try that again.** {e}", icon="🎤")
        return None


def recorder(label, key):
    """A microphone recorder with a file-upload fallback."""
    clip = st.audio_input(label, key=f"{key}_mic")
    with st.expander("No microphone? Upload a recording instead"):
        upload = st.file_uploader("Audio file", type=AUDIO_TYPES, key=f"{key}_file")
    return clip or upload


def reading_tab():
    """Read a text once and get one verdict."""
    ready = predict.ready(READING_TASKS)
    if not ready:
        st.info("No reading check is available yet. The “aaah” tab works.", icon="⏳")
        return
    text_id = st.selectbox("Text to read", list(TEXTS), format_func=lambda t: TEXTS[t]["title"], key="scr_text")
    st.markdown(f"<div class='reading'>{html.escape(TEXTS[text_id]['text'])}</div>", unsafe_allow_html=True)
    clip = recorder("Record yourself reading the whole text", "scr_read")
    if st.button("Check my reading", type="primary", disabled=clip is None):
        wav = clean(clip)
        if wav is not None:
            show_verdict(ready[0], wav)
    reliability(ready)


def vowel_tab():
    """Hold "aaah" and get one verdict."""
    if predict.load("svd") is None:
        st.info("The vowel check is still being trained. Refresh this page in a few minutes.", icon="⏳")
        return
    st.markdown("Take a breath and say **“aaah”** at a comfortable pitch and loudness, as steadily as you can, "
                "for **3 to 5 seconds**.")
    clip = recorder("Record your “aaah”", "scr_vowel")
    if st.button("Check my voice", type="primary", disabled=clip is None):
        wav = clean(clip, vowel=True)
        if wav is not None:
            show_verdict("svd", wav)
            with st.expander("Voice measures"):
                values = voice_quality(predict.middle(wav))
                st.markdown("\n".join(f"- {name}: **{value:.2f}**" for name, value in zip(VOICE_QUALITY, values)))
    reliability(["svd"])


st.title("🎙️ VoiceDrift")
st.caption("Record your voice and see which voice condition it is most similar to, using research recordings of "
           "people with voice conditions. Not a diagnosis, and it makes mistakes.")
st.sidebar.caption("Research prototype, not a medical device. Audio is processed locally.")

reading, vowel = st.tabs(["🗣️ Read a text", "🎵 Hold “aaah”"])
with reading:
    reading_tab()
with vowel:
    vowel_tab()

with st.expander("About the research data"):
    for task in TASKS.values():
        st.markdown(f"**{task['title']}** compares with {task['dataset']}. It looks for {task['pattern']}.")
        st.caption(f"Data credit: {task['credit']}")
