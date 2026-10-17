"""Voice screening (research): compare a reading or an "aaah" with research datasets. Not a diagnosis.

Opened from the sidebar of the main app (streamlit run app.py).
"""
import html

import streamlit as st

from voice_checker.audio.quality import QualityError
from voice_checker.screening import READING_TASKS, TASKS, describe, predict
from voice_checker.screening.features import VOICE_QUALITY, voice_quality
from voice_checker.texts import TEXTS

AUDIO_TYPES = ["wav", "flac", "ogg", "mp3"]
READING_TASKS = ["torgo", "svd_phrase"]  # both run on one reading
NOTES = {
    "torgo": "TORGO doesn't record which speakers have cerebral palsy and which have ALS, so this check can't name "
             "a condition; it only looks for dysarthria-like speech.",
    "svd_phrase": "Trained on a short German sentence; voice quality is fairly independent of language, but reading "
                  "English is still a mismatch.",
}


def band(bundle, prob):
    """(label, banner) for a score, using the thresholds chosen in training (20% / 5% of healthy flagged)."""
    t = bundle.get("thresholds", {"some": 0.5, "high": 0.8})
    if prob >= t["high"]:
        return "High similarity", st.error
    if prob >= t["some"]:
        return "Some similarity", st.warning
    return "Low similarity", st.success


def model_card(task):
    """The model's name and how it did on speakers it had never heard, in plain words."""
    bundle = predict.load(task)
    some, high = bundle["speaker_metrics"], bundle.get("high_metrics")
    text = (f"**{TASKS[task]['title']}.** Tested on {bundle['n_groups']} people it had never heard (healthy people "
            f"matched for age and sex): **Some similarity** or higher was given to **{some['sensitivity']:.0%}** of "
            f"people with a condition and to {1 - some['specificity']:.0%} of healthy people")
    if high:
        text += (f"; **High similarity** to {high['sensitivity']:.0%} of people with a condition and "
                 f"{1 - high['specificity']:.0%} of healthy people")
    text += "."
    if bundle.get("setup_auc") is not None and bundle["setup_auc"] >= 0.75:
        text += " ⚠️ It failed the recording-setup check, so treat its scores with extra caution."
    if task in NOTES:
        text += " " + NOTES[task]
    st.caption(text)


def clean(clip, vowel=False):
    """Quality-check a reading or an "aaah"; returns the cleaned audio, or None after showing the problem."""
    try:
        # The models were trained on 1-2 s vowels and ~2 s sentences, so short clips are fine here.
        wav, _ = check_vowel(clip) if vowel else check_quality(clip, min_duration_s=1.5,
                                                                   hint="Please read at least one full sentence.")
        return wav
    except QualityError as e:
        st.error(f"**Let's try that again.** {e}", icon="🎤")
        return None


def show_result(task, prob):
    """The score, its band, and what it does and doesn't mean; returns the band's label."""
    label, banner = band(predict.load(task), prob)
    banner(f"**{label}** to research recordings of {TASKS[task]['pattern']} · score {prob:.0%}")
    if label != "Low similarity":
        st.markdown("Your recording shares some patterns with that group. **This is not a diagnosis**: tiredness, "
                    "a cold, your microphone or your accent can do this too, and the model makes mistakes. If you "
                    "have noticed changes in your speech or voice, a doctor or speech-language therapist can check properly.")
    else:
        st.markdown("Your recording is closer to the speakers without these patterns. A low score doesn't rule "
                    "anything out: if you're worried about your speech or voice, talk to a doctor or speech-language therapist.")
    return label


def show_breakdown(task, wav):
    """Which research group the voice is closest to, each with how often that guess was right in testing."""
    rows = predict.condition_breakdown(task, wav)
    if not rows:
        return
    groups = predict.load(task)["condition_groups"]
    st.markdown("**Closest research group**")
    for name, prob, right in rows:
        st.progress(prob, text=f"**{name}** · {prob:.0%} · in testing, this first guess was right {right:.0%} of the time")
    st.info(f"This breakdown is only slightly better than guessing: its first guess was right "
            f"{groups['balanced']:.0%} of the time on average, where guessing would be {1 / len(rows):.0%}. "
            "Doctors tell these conditions apart by looking at the vocal folds, which no recording can replace.",
            icon="ℹ️")


def result_block(task, wav):
    """Score a cleaned clip with one model and show its band, explanation and breakdown."""
    st.markdown(f"#### {TASKS[task]['title']}")
    with st.spinner("Comparing with the research recordings…"):
        prob = predict.score(task, wav)
    if show_result(task, prob) != "Low similarity":
        show_breakdown(task, wav)
    elif predict.load(task).get("condition_groups"):
        st.caption("The closest-research-group breakdown is only shown from “Some similarity” up; "
                   "with a low score it isn't meaningful.")


def recorder(label, key):
    """A microphone recorder with a file-upload fallback."""
    clip = st.audio_input(label, key=f"{key}_mic")
    with st.expander("No microphone? Upload a recording instead"):
        upload = st.file_uploader("Audio file", type=AUDIO_TYPES, key=f"{key}_file")
    return clip or upload


def reading_tab():
    """Read a text once; every trained reading model gives its result."""
    ready = [t for t in READING_TASKS if predict.load(t) and not TASKS[t].get("disabled")]
    for task in READING_TASKS:
        if TASKS[task].get("disabled"):
            st.caption(f"🚫 **{TASKS[task]['title']}** is switched off: {TASKS[task]['disabled']}")
        elif task not in ready:
            st.caption(f"⏳ {TASKS[task]['title']} is still being trained; refresh later to add it.")
    if not ready:
        st.info("No reading check is available yet. The “aaah” tab works.", icon="⏳")
        return
    for task in ready:
        model_card(task)
    text_id = st.selectbox("Text to read", list(TEXTS), format_func=lambda t: TEXTS[t]["title"], key="scr_text")
    st.markdown(f"<div class='reading'>{html.escape(TEXTS[text_id]['text'])}</div>", unsafe_allow_html=True)
    clip = recorder("Record yourself reading the whole text", "scr_read")
    if st.button("Check my reading", type="primary", disabled=clip is None):
        wav = clean(clip)
        if wav is not None:
            for task in ready:
                result_block(task, wav)


def vowel_tab():
    """Hold "aaah"; compare with the Saarbrücken Voice Database vowels."""
    if predict.load("svd") is None:
        st.info("The vowel check is still being trained. Refresh this page in a few minutes.", icon="⏳")
        return
    model_card("svd")
    st.markdown("Take a breath and say **“aaah”** at a comfortable pitch and loudness, as steadily as you can, "
                "for **3 to 5 seconds**.")
    clip = recorder("Record your “aaah”", "scr_vowel")
    if st.button("Check my voice", type="primary", disabled=clip is None):
        wav = clean(clip, vowel=True)
        if wav is not None:
            result_block("svd", wav)
            with st.expander("Voice measures"):
                values = voice_quality(predict.middle(wav))
                st.markdown("\n".join(f"- {name}: **{value:.2f}**" for name, value in zip(VOICE_QUALITY, values)))


st.title("🩺 Voice screening (research)")
st.warning("**Research demo, not a diagnosis.** These checks compare your recording with research recordings of "
           "people with speech or voice conditions. They can't tell for sure which condition someone has, they were "
           "trained on limited data, and they make mistakes.", icon="⚠️")
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
    st.markdown("Reports from training are in `models/screening/`. The main VoiceDrift page stays the better "
                "signal for one person over time: it compares you with your own baseline.")
