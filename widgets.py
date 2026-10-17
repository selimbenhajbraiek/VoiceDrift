"""UI pieces shared by the main page (app.py) and the test lab (test_lab.py)."""
import html

from features.transcript import align

CSS = """
<style>
.reading { font-size: 1.15rem; line-height: 1.7; padding: 1rem 1.25rem; border-radius: 0.5rem;
           border: 1px solid rgba(128,128,128,0.3); background: rgba(128,128,128,0.06); }
.diff { line-height: 1.9; }
.diff .sub { background: rgba(208,59,59,0.18); border-radius: 4px; padding: 0 3px; }
.diff .del { color: #898781; text-decoration: line-through; }
.diff .ins { background: rgba(250,178,25,0.25); border-radius: 4px; padding: 0 3px; }
.diff s { opacity: 0.6; }
</style>
"""

DIFF_LEGEND = ("<span class='diff'><span class='sub'>misread</span> "
               "<span class='del'>skipped</span> <span class='ins'>extra</span></span>")


def transcript_html(expected, transcript):
    """The heard words, with misread, skipped and extra words highlighted."""
    _, diff = align(expected, transcript)
    parts = []
    for op, exp, heard in diff:
        exp, heard = html.escape(exp or ""), html.escape(heard or "")
        if op == "ok":
            parts.append(exp)
        elif op == "sub":
            parts.append(f"<span class='sub' title='expected: {exp}'><s>{exp}</s> {heard}</span>")
        elif op == "del":
            parts.append(f"<span class='del' title='skipped'>{exp}</span>")
        else:
            parts.append(f"<span class='ins' title='extra word'>{heard}</span>")
    return "<div class='diff'>" + " ".join(parts) + "</div>"
