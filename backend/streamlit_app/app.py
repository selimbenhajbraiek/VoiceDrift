"""VoiceDrift: read a short text aloud and see how your voice compares with your own baseline.

Run:  streamlit run backend/streamlit_app/app.py   (the sidebar also links to the Test lab page)
"""
import html
import os
from datetime import datetime
import sys

from pathlib import Path
import plotly.graph_objects as go
import streamlit as st

# Streamlit runs this file as a script, so put the repository on the import path for `backend` and `voice_checker`.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.streamlit_app import widgets
from voice_checker import config, drift, explain, storage
from voice_checker.analyze import analyze
from voice_checker.audio.quality import QualityError
from voice_checker.demo import TEXT_ID as DEMO_TEXT_ID
from voice_checker.demo import load_demo
from voice_checker.texts import TEXTS

STATUS_COLORS = {"Stable": "#0ca30c", "Watch": "#fab219", "Changed": "#d03b3b"}
STATUS_BANNERS = {"Stable": (st.success, "✅"), "Watch": (st.warning, "👀"), "Changed": (st.error, "⚠️")}
MUTED = "#898781"
FORMATS = {  # how to print each biomarker's value
    "embedding": "{:.3f}", "wpm": "{:.0f} wpm", "wer": "{:.0%}", "filler_count": "{:.0f}",
    "f0_mean_hz": "{:.0f} Hz", "f0_std_st": "{:.1f} st", "pause_count": "{:.0f}", "pause_ratio": "{:.0%}",
}
TREND_KEYS = ["wpm", "pause_ratio", "f0_std_st"]


# --- Helpers ----------------------------------------------------------------
def is_dark():
    """True when Streamlit renders in dark mode."""
    return getattr(st.context.theme, "type", "light") == "dark"


def series_color():
    """Data line color, stepped for the current theme."""
    return "#3987e5" if is_dark() else "#2a78d6"


def surface_color():
    """Page background, used as the ring around markers."""
    return "#0e1117" if is_dark() else "#ffffff"


def fmt(key, value):
    """Format a biomarker value for display."""
    return FORMATS[key].format(value)


def when(timestamp):
    """ISO timestamp -> datetime."""
    return datetime.fromisoformat(timestamp)


def use_demo():
    """Button callback: create the demo user and switch the form to it."""
    load_demo()
    st.session_state.user_name = config.DEMO_USER
    st.session_state.text_id = DEMO_TEXT_ID


@st.cache_data(show_spinner=False)
def cached_summary(z_items, status, persistent, use_claude):
    """Summaries are cached so Streamlit reruns don't call Claude again."""
    return explain.summarize(dict(z_items), status, persistent, use_claude)


# --- Charts -----------------------------------------------------------------
def add_points(fig, x, y, rows, hover):
    """Draw the line, hollow baseline markers and filled reading markers."""
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color=series_color(), width=2),
                             hoverinfo="skip", showlegend=False))
    for is_base, name in [(True, "Baseline"), (False, "Compared with baseline")]:
        idx = [i for i, r in enumerate(rows) if r["is_baseline"] == is_base]
        fig.add_trace(go.Scatter(
            x=[x[i] for i in idx], y=[y[i] for i in idx], mode="markers", name=name,
            marker=dict(size=10, color=surface_color() if is_base else series_color(),
                        line=dict(color=MUTED if is_base else surface_color(), width=2)),
            customdata=[rows[i]["status"] for i in idx], hovertemplate=hover,
        ))


def index_chart(rows):
    """Overall drift index over time, on top of the Stable / Watch / Changed bands."""
    x = [when(r["timestamp"]) for r in rows]
    y = [r["index"] for r in rows]
    top = max(5.0, max(y) * 1.15)
    fig = go.Figure()
    bands = [(0, config.WATCH_INDEX, "Stable"), (config.WATCH_INDEX, config.CHANGED_INDEX, "Watch"),
             (config.CHANGED_INDEX, top, "Changed")]
    for lo, hi, name in bands:
        fig.add_hrect(y0=lo, y1=hi, fillcolor=STATUS_COLORS[name], opacity=0.12, line_width=0, layer="below")
        fig.add_annotation(xref="paper", x=1.01, xanchor="left", y=(lo + hi) / 2, text=name,
                           showarrow=False, font=dict(color=MUTED, size=12))
    add_points(fig, x, y, rows, "%{x|%b %d, %H:%M}<br>Index %{y:.2f} · %{customdata}<extra></extra>")
    fig.add_annotation(x=x[-1], y=y[-1], text=f"{y[-1]:.1f}", showarrow=False, yshift=16)
    fig.update_layout(height=320, margin=dict(l=10, r=70, t=10, b=10), hovermode="closest",
                      legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0))
    fig.update_yaxes(range=[0, top], title="Drift index", showgrid=False, zeroline=False)
    fig.update_xaxes(showgrid=False)
    return fig


def biomarker_chart(key, sessions, rows, baseline):
    """One biomarker over time with the baseline's usual range (mean ± 1 SD) shaded."""
    label, unit = config.LABELS[key]
    x = [when(s["timestamp"]) for s in sessions]
    y = [s["biomarkers"][key] for s in sessions]
    mean, sd = baseline[key]["mean"], baseline[key]["std"]
    fig = go.Figure()
    fig.add_hrect(y0=mean - sd, y1=mean + sd, fillcolor=series_color(), opacity=0.10, line_width=0, layer="below")
    fig.add_hline(y=mean, line=dict(color=MUTED, width=1))
    tick = ".0%" if key == "pause_ratio" else ".1f" if key == "f0_std_st" else ".0f"
    add_points(fig, x, y, rows, "%{x|%b %d}<br>%{y:" + tick + "}<extra></extra>")
    fig.update_layout(height=230, margin=dict(l=10, r=10, t=36, b=10), showlegend=False,
                      title=dict(text=f"{label} ({unit})", font=dict(size=14), x=0, xanchor="left"))
    fig.update_yaxes(tickformat=tick, showgrid=False, zeroline=False, nticks=4)
    fig.update_xaxes(showgrid=False, nticks=3, tickformat="%b %d")
    return fig


# --- Page sections ----------------------------------------------------------
def sidebar():
    """Disclaimer, privacy note and demo button. Returns whether to use Claude."""
    with st.sidebar:
        st.header("🎙️ VoiceDrift")
        st.warning("**Research prototype, not a medical device.** VoiceDrift describes changes "
                   "in your voice; it does not diagnose anything.", icon="⚠️")
        st.info("**Audio is processed locally** on this computer and never uploaded. Only the "
                "measurements are saved, in `voice_checker/data/users/`.", icon="🔒")
        use_claude = False
        if os.environ.get("ANTHROPIC_API_KEY"):
            use_claude = st.toggle("Friendlier summary by Claude", value=True)
            st.caption("When on, only the status and the direction of the biggest changes are sent "
                       "to the Claude API, never audio, transcripts or names.")
        st.divider()
        st.button("Load demo data", on_click=use_demo, width="stretch")
        st.caption(f"Creates **{config.DEMO_USER}** with 3 baseline and 4 drifting readings of "
                   f"“{TEXTS[DEMO_TEXT_ID]['title']}”.")
    return use_claude


def record_section(name, text_id):
    """Show the text, take a recording or upload, analyze it and save the session."""
    st.subheader("1 · Read this aloud")
    st.markdown(f"<div class='reading'>{html.escape(TEXTS[text_id]['text'])}</div>", unsafe_allow_html=True)
    st.write("")
    n = st.session_state.setdefault("rec_n", 0)  # bumped after saving to reset the widgets
    clip = st.audio_input("Record yourself reading the whole text", key=f"rec_{n}")
    with st.expander("No microphone? Upload a recording instead"):
        upload = st.file_uploader("Audio file", type=["wav", "flac", "ogg", "mp3"], key=f"up_{n}")
    clip = clip or upload
    if st.button("Analyze and save", type="primary", disabled=clip is None):
        with st.spinner("Analyzing your voice… the first run downloads the models (about a minute)."):
            try:
                session = analyze(clip, text_id)
            except QualityError as e:
                st.error(f"**Let's try that again.** {e}", icon="🎤")
                return
        storage.add_session(name, session)
        q = session["quality"]
        snr = f", background noise {q['snr_db']:.0f} dB below your voice" if q["snr_db"] is not None else ""
        st.session_state.flash = f"Saved a {q['duration_s']:.0f} s reading{snr}."
        st.session_state.rec_n = n + 1
        st.rerun()
    if "flash" in st.session_state:
        st.success(st.session_state.pop("flash"), icon="💾")


def changes_table(session, row, baseline):
    """Markdown table of the biomarkers that moved most, with direction and explanation."""
    lines = ["| Biomarker | This reading | Your usual | Change |", "|---|---|---|---|"]
    for key, z in drift.top_changes(row["z"]):
        if key == "embedding":
            now = drift.cosine_distance(session["embedding"], baseline["embedding"]["centroid"])
            usual = baseline["embedding"]["mean"]
        else:
            now, usual = session["biomarkers"][key], baseline[key]["mean"]
        arrow = "↑" if z > 0 else "↓"
        lines.append(f"| **{config.LABELS[key][0]}**<br><small>{explain.MEANING[key]}</small> "
                     f"| {fmt(key, now)} | {fmt(key, usual)} | {arrow} {explain.describe(key, z)} (z {z:+.1f}) |")
    return "\n".join(lines)


def all_scores_table(sessions, rows):
    """Every session's index, status and biomarkers: the table view behind the charts."""
    table = []
    for s, r in zip(sessions, rows):
        entry = {"When": when(s["timestamp"]).strftime("%b %d %H:%M"), "Status": r["status"],
                 "Index": round(r["index"], 2)}
        entry.update({config.LABELS[k][0]: fmt(k, s["biomarkers"][k]) for k in drift.SCALARS})
        table.append(entry)
    return table


def reading_label(session, row):
    """'Oct 12, 09:06 · Watch', plus the test-bench label when there is one."""
    text = f"{when(session['timestamp']):%b %d, %H:%M} · {row['status']}"
    return text + (f" · {session['label']}" if session.get("label") else "")


def results_section(name, text_id, sessions, use_claude):
    """Baseline progress, or the status, explanation, transcript and trend charts."""
    st.subheader("2 · Your results")
    expected = TEXTS[text_id]["text"]
    scored = drift.score_history(sessions)
    if scored is None:
        st.info(f"**Building your baseline ({len(sessions)}/{config.BASELINE_N})** · read this text "
                f"{config.BASELINE_N - len(sessions)} more time(s), ideally on different days, in a quiet "
                "room with the same microphone.", icon="📏")
        st.progress(len(sessions) / config.BASELINE_N)
        if sessions:
            st.markdown("**What we heard last time** · " + widgets.DIFF_LEGEND, unsafe_allow_html=True)
            st.markdown(widgets.transcript_html(expected, sessions[-1]["transcript"]), unsafe_allow_html=True)
        return

    baseline, rows = scored
    pick = st.selectbox("Reading to show", range(len(sessions)), index=len(sessions) - 1,
                        key=f"pick_{name}_{text_id}_{len(sessions)}",
                        format_func=lambda i: reading_label(sessions[i], rows[i]))
    session, row = sessions[pick], rows[pick]
    if row["is_baseline"]:
        st.success(f"**Baseline complete ({config.BASELINE_N}/{config.BASELINE_N}).** Your next "
                   "reading of this text will be compared with it.", icon="📏")
    else:
        banner, icon = STATUS_BANNERS[row["status"]]
        banner(f"**{row['status']}** · drift index {row['index']:.1f} "
               f"(Stable < {config.WATCH_INDEX:g}, Watch < {config.CHANGED_INDEX:g}, Changed above)", icon=icon)
        persistent = drift.is_persistent(rows[: pick + 1])
        if persistent:
            st.error(f"**Persistent change:** your last {config.PERSIST_K} readings were all Watch or "
                     "Changed. Consider resting, and if it continues, checking in with a healthcare "
                     "professional.", icon="🔔")
        summary, source = cached_summary(tuple(sorted(row["z"].items())), row["status"], persistent, use_claude)
        st.markdown(summary)
        st.caption("Summary written by Claude from your numbers." if source == "claude"
                   else "Summary built from templates.")
        st.markdown("**What moved most**")
        st.markdown(changes_table(session, row, baseline), unsafe_allow_html=True)

    st.markdown("**What we heard** · " + widgets.DIFF_LEGEND, unsafe_allow_html=True)
    st.markdown(widgets.transcript_html(expected, session["transcript"]), unsafe_allow_html=True)
    with st.expander("Exact transcript"):
        st.write(session["transcript"])

    st.markdown("**Trend**")
    st.plotly_chart(index_chart(rows), config={"displayModeBar": False},
                    alt="Line chart of the overall drift index for each reading, over Stable, Watch and Changed bands.")
    for col, key in zip(st.columns(len(TREND_KEYS)), TREND_KEYS):
        with col:
            st.plotly_chart(biomarker_chart(key, sessions, rows, baseline), config={"displayModeBar": False},
                            alt=f"{config.LABELS[key][0]} for each reading, with the usual range shaded.")
    st.caption("Shaded band in the small charts = your usual range (baseline mean ± 1 SD). Hollow points are baseline readings.")
    with st.expander("All readings as a table"):
        st.dataframe(all_scores_table(sessions, rows), hide_index=True)


# --- Pages ------------------------------------------------------------------
def main_page():
    """The VoiceDrift flow: name and text, recording, then results."""
    use_claude = sidebar()
    st.title("🎙️ VoiceDrift")
    st.caption("Read a short text aloud. VoiceDrift compares your voice with your own baseline and tells you what changed.")

    name = st.text_input("Your name", key="user_name", placeholder="e.g. Sam").strip()
    text_id = st.selectbox("Text to read", list(TEXTS), key="text_id", format_func=lambda t: TEXTS[t]["title"])
    if not name:
        st.info("Enter your name to start, or click **Load demo data** in the sidebar.", icon="👋")
        st.stop()

    record_section(name, text_id)
    st.divider()
    results_section(name, text_id, storage.sessions_for_text(storage.load_user(name), text_id), use_claude)


st.set_page_config(page_title="VoiceDrift", page_icon="🎙️", layout="centered")
st.markdown(widgets.CSS, unsafe_allow_html=True)
st.navigation([
    st.Page(main_page, title="VoiceDrift", icon="🎙️", default=True),
    st.Page("screening_page.py", title="Voice screening (research)", icon="🩺"),
    st.Page("test_lab.py", title="Test lab", icon="🧪"),
]).run()
