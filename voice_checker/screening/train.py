"""Train and test a research screening model on TORGO or the Saarbrücken Voice Database.

Run:  python -m voice_checker.screening.train svd   E:/VoiceDrift-data/svd     (voice-disorder-like voice, "aaah")
      python -m voice_checker.screening.train torgo E:/VoiceDrift-data/torgo   (dysarthria-like speech, reading)

Testing is speaker-independent: no speaker is ever in both the training and the test part.
Training weights balance the sexes within each class, so the model can't simply learn
"female voice" when one class has more women; results are also reported per sex. A
recording-setup check trains the same model on the silent parts of each clip only: if
silence alone separates the groups, the scores partly reflect the recording setup.
Outputs go to voice_checker/models/screening/.
"""
import argparse
import time
from datetime import datetime

import joblib
import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import LeaveOneGroupOut, StratifiedGroupKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from voice_checker import config
from voice_checker.audio.quality import load_audio
from voice_checker.screening import MODEL_DIR, TASKS
from voice_checker.screening.datasets import LOADERS
from voice_checker.screening.features import feature_vector, silence_vector

SETUP_WARNING_AUC = 0.75
FEATURE_SETS = {  # columns of screening.features.feature_vector
    "all": (0, 223),
    "acoustic": (192, 223),   # MFCC statistics + jitter, shimmer, HNR, pitch
    "embedding": (0, 192),    # ECAPA voice embedding only
}


def make_model():
    """Standardize, then a strongly regularized logistic regression (balance comes from sample weights)."""
    return make_pipeline(SimpleImputer(), StandardScaler(), LogisticRegression(C=0.05, max_iter=5000))


def extract(task, items, refresh=False):
    """Features, silence features, labels, groups, sexes and ages, cached in models/screening/<task>_features.npz."""
    cache = MODEL_DIR / f"{task}_features.npz"
    if cache.exists() and not refresh:
        d = np.load(cache, allow_pickle=False)
        return {k: d[k] for k in d.files}
    rows = {k: [] for k in ("X", "S", "y", "groups", "sex", "age", "condition")}
    start = time.time()
    for i, (path, label, group, meta) in enumerate(items, 1):
        try:
            wav = load_audio(str(path))
            if len(wav) < 0.3 * config.SAMPLE_RATE:
                continue
            silence = silence_vector(wav)
            for key, value in (("X", feature_vector(wav)), ("S", silence if silence is not None else np.full(26, np.nan)),
                               ("y", label), ("groups", group), ("sex", meta["sex"]),
                               ("age", meta["age"] if meta["age"] is not None else np.nan),
                               ("condition", meta["condition"])):
                rows[key].append(value)
        except Exception as e:  # a broken file shouldn't stop a long run
            print(f"  skipped {path.name}: {e}")
        if i % 100 == 0:
            print(f"  {i}/{len(items)} recordings ({time.time() - start:.0f} s)", flush=True)
    data = {k: np.array(v) for k, v in rows.items()}
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    np.savez(cache, **data)
    return data


def strata(sex, age):
    """Sex x 15-year age band for each recording (sex only when the age is unknown)."""
    return np.array([f"{s}-{int(a // 15) if np.isfinite(a) else 'na'}" for s, a in zip(sex, age)])


def balance_weights(y, sex, age):
    """Weights that match the controls' age and sex mix to the condition group's, with equal class totals.

    Controls in a stratum get P(stratum | condition) / P(stratum | controls); strata without
    any condition speaker get weight 0. Without this, a model could score well by spotting
    older or female voices whenever the two groups differ in age or sex.
    """
    s = strata(sex, age)
    w = np.ones(len(y))
    for stratum in set(s):
        cond, ctrl = (s == stratum) & (y == 1), (s == stratum) & (y == 0)
        if ctrl.any():
            w[ctrl] = (cond.sum() / (y == 1).sum()) / (ctrl.sum() / (y == 0).sum())
    for label in (0, 1):  # equal total weight per class
        w[y == label] *= len(y) / (2 * w[y == label].sum())
    return w


def out_of_fold(X, y, groups, weights):
    """Probabilities for every recording from a model that never saw its speaker."""
    cv = LeaveOneGroupOut() if len(set(groups)) <= 30 else StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
    return cross_val_predict(make_model(), X, y, groups=groups, cv=cv, method="predict_proba",
                             params={"logisticregression__sample_weight": weights})[:, 1]


def scores(y, p, w=None, threshold=0.5):
    """AUC, sensitivity, specificity and balanced accuracy, optionally weighted."""
    w = np.ones(len(y)) if w is None else w
    flagged = p >= threshold
    rate = lambda mask: float(np.sum(w[mask & flagged]) / np.sum(w[mask])) if np.sum(w[mask]) > 0 else float("nan")
    sens, spec = rate(y == 1), 1 - rate(y == 0)
    auc = float(roc_auc_score(y, p, sample_weight=w)) if len(set(y[w > 0])) == 2 else float("nan")
    return {"auc": auc, "sensitivity": sens, "specificity": spec, "balanced_accuracy": (sens + spec) / 2,
            "n": int(np.sum(w > 0))}


def control_quantile(spk, q):
    """The score below which a (weighted) fraction q of control speakers fall."""
    controls = spk["y"] == 0
    order = np.argsort(spk["p"][controls])
    p, w = spk["p"][controls][order], spk["w"][controls][order]
    cum = np.cumsum(w) / w.sum()
    return float(p[min(np.searchsorted(cum, q), len(p) - 1)])


def per_group(d, p, weights):
    """One row per speaker: label, sex, age, matching weight and mean probability."""
    ids = sorted(set(d["groups"]))
    first = lambda values: np.array([values[d["groups"] == g][0] for g in ids])
    return {"y": first(d["y"]), "sex": first(d["sex"]), "age": first(d["age"]), "w": first(weights),
            "p": np.array([p[d["groups"] == g].mean() for g in ids])}


def setup_check(d):
    """AUC of a model that only hears the silent parts; None if most clips have no silence."""
    ok = ~np.isnan(d["S"]).any(axis=1)
    if ok.mean() < 0.5 or len(set(d["y"][ok])) < 2:
        return None
    w = balance_weights(d["y"][ok], d["sex"][ok], d["age"][ok])
    return float(roc_auc_score(d["y"][ok], out_of_fold(d["S"][ok], d["y"][ok], d["groups"][ok], w), sample_weight=w))


CONDITION_GROUPS = {  # SVD folders -> groups of the per-condition breakdown (reflux has too few recordings)
    "healthy": "Healthy",
    "vocal_fold_paralysis": "Vocal fold paralysis",
    "laryngitis": "Laryngitis",
    "nodules": "Nodules or polyps",
    "polyp": "Nodules or polyps",
}


def group_weights(labels, sex, age):
    """Weights matching every group to the pooled condition groups' age and sex mix, with equal group totals."""
    s, target = strata(sex, age), labels != "Healthy"
    w = np.zeros(len(labels))
    for group in set(labels):
        in_group = labels == group
        for stratum in set(s[in_group]):
            cell = in_group & (s == stratum)
            w[cell] = ((target & (s == stratum)).sum() / target.sum()) / (cell.sum() / in_group.sum())
    for group in set(labels):
        total = w[labels == group].sum()
        if total > 0:
            w[labels == group] *= len(labels) / (len(set(labels)) * total)
    return w


def train_condition_groups(d, start, stop):
    """Which research group a voice is closest to, with how often the first guess is right per group.

    Returns (bundle entry, Markdown section). Speaker-independent 5-fold test, matched weights.
    """
    keep = np.isin(d["condition"], list(CONDITION_GROUPS))
    labels = np.array([CONDITION_GROUPS[c] for c in d["condition"][keep]])
    X, groups = d["X"][keep][:, start:stop], d["groups"][keep]
    w = group_weights(labels, d["sex"][keep], d["age"][keep])
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
    proba = cross_val_predict(make_model(), X, labels, groups=groups, cv=cv, method="predict_proba",
                              params={"logisticregression__sample_weight": w})
    classes = np.unique(labels)  # cross_val_predict orders the columns like this
    guess = classes[proba.argmax(axis=1)]
    right = {c: float(np.sum(w[(labels == c) & (guess == c)]) / np.sum(w[labels == c])) for c in classes}
    balanced = float(np.mean(list(right.values())))
    model = make_model().fit(X, labels, logisticregression__sample_weight=w)
    lines = ["", "## Per-condition breakdown", "",
             f"Which group the model's first guess picks (speaker-independent, matched; chance = {1 / len(classes):.0%}):", "",
             "| Group | Recordings | First guess right |", "| --- | --- | --- |"]
    lines += [f"| {c} | {int(np.sum(labels == c))} | {right[c]:.0%} |" for c in classes]
    lines.append(f"\nAverage over groups: {balanced:.0%}.")
    return {"model": model, "classes": list(model.classes_), "right": right, "balanced": balanced}, "\n".join(lines) + "\n"


def report(task, d, spk, setup_auc):
    """The evaluation as Markdown, including the sex and age balance and per-sex results."""
    t = TASKS[task]
    row = lambda name, m: (f"| {name} | {m['n']} | {m['auc']:.2f} | {m['sensitivity']:.0%} | "
                           f"{m['specificity']:.0%} | {m['balanced_accuracy']:.0%} |")
    lines = [f"# {t['title']}: research screening model ({task})", "", f"Dataset: {t['dataset']}.", "",
             "| Group | Speakers | Women | Mean age |", "| --- | --- | --- | --- |"]
    for label, name in ((1, "Condition group"), (0, "Controls")):
        m = spk["y"] == label
        age = np.nanmean(spk["age"][m]) if np.isfinite(spk["age"][m]).any() else float("nan")
        lines.append(f"| {name} | {m.sum()} | {np.mean(spk['sex'][m] == 'f'):.0%} | "
                     + ("n/a" if np.isnan(age) else f"{age:.0f}") + " |")
    lines += ["", f"Speaker-independent test ({len(d['y'])} recordings; the model never heard the tested speaker).",
              "“Matched” weighs the controls to the condition group's age and sex mix: that is the honest result.", "",
              "| Speakers | n | AUC | Sensitivity | Specificity | Balanced accuracy |", "| --- | --- | --- | --- | --- | --- |",
              row("All, as recorded", scores(spk["y"], spk["p"])),
              row("**All, matched**", scores(spk["y"], spk["p"], spk["w"]))]
    for sex, name in (("f", "Women, matched"), ("m", "Men, matched")):
        m = spk["sex"] == sex
        if m.any():
            lines.append(row(name, scores(spk["y"][m], spk["p"][m], spk["w"][m])))
    lines.append("")
    if setup_auc is None:
        lines.append("Recording-setup check: not enough silence in the clips to run it.")
    elif setup_auc >= SETUP_WARNING_AUC:
        lines.append(f"⚠️ Recording-setup check: silence alone reaches AUC {setup_auc:.2f}. The model may partly "
                     "learn the recording setup rather than the voice; treat its scores with extra caution.")
    else:
        lines.append(f"Recording-setup check: silence alone reaches AUC {setup_auc:.2f} (below {SETUP_WARNING_AUC}), OK.")
    return "\n".join(lines) + "\n"


def main():
    """Load the dataset, extract features, test, train the final model and save it with its report."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task", choices=list(TASKS))
    parser.add_argument("root", help="folder holding the dataset")
    parser.add_argument("--refresh", action="store_true", help="re-extract features instead of using the cache")
    parser.add_argument("--features", choices=[*FEATURE_SETS, "best"], default="best",
                        help="which features the model uses; 'best' tries each and keeps the best matched AUC")
    args = parser.parse_args()

    items = LOADERS[args.task](args.root)
    if not items:
        raise SystemExit(f"No recordings found under {args.root}; see the README for the expected folders.")
    print(f"{len(items)} recordings from {len({it[2] for it in items})} speakers; extracting features…")
    d = extract(args.task, items, args.refresh)
    weights = balance_weights(d["y"], d["sex"], d["age"])

    tried = {}
    for name in (FEATURE_SETS if args.features == "best" else [args.features]):
        start, stop = FEATURE_SETS[name]
        spk = per_group(d, out_of_fold(d["X"][:, start:stop], d["y"], d["groups"], weights), weights)
        tried[name] = (scores(spk["y"], spk["p"], spk["w"]), spk)
        print(f"  features '{name}': matched AUC {tried[name][0]['auc']:.2f}", flush=True)
    best = max(tried, key=lambda n: tried[n][0]["auc"])
    spk = tried[best][1]
    start, stop = FEATURE_SETS[best]
    # The app's bands start where 20% ("some") and 5% ("high") of matched controls would be flagged.
    thresholds = {"some": control_quantile(spk, 0.80), "high": control_quantile(spk, 0.95)}
    operating = {band: scores(spk["y"], spk["p"], spk["w"], threshold=t) for band, t in thresholds.items()}

    setup_auc = setup_check(d)
    note = f"\n\nFeatures: {best}."
    if len(tried) > 1:
        note += (" Picked as the best matched AUC of " + ", ".join(f"{n} {m['auc']:.2f}" for n, (m, _) in tried.items())
                 + " (choosing on the same test makes the result slightly optimistic).")
    text = report(args.task, d, spk, setup_auc).replace("\n", note, 1)
    text += ("\nBands used by the app (speaker level, matched; thresholds chosen on the same test):\n\n"
             "| Band starts at | Score | Flags people with a condition | Flags matched controls |\n| --- | --- | --- | --- |\n")
    for band, name in (("some", "Some similarity"), ("high", "High similarity")):
        m = operating[band]
        text += f"| {name} | {thresholds[band]:.2f} | {m['sensitivity']:.0%} | {1 - m['specificity']:.0%} |\n"

    condition_groups = None
    if args.task.startswith("svd"):
        condition_groups, section = train_condition_groups(d, start, stop)
        text += section

    model = make_model().fit(d["X"][:, start:stop], d["y"], logisticregression__sample_weight=weights)
    joblib.dump({"model": model, "task": args.task, "columns": (start, stop), "features": best,
                 "condition_groups": condition_groups,
                 "thresholds": thresholds, "speaker_metrics": operating["some"], "high_metrics": operating["high"],
                 "auc": tried[best][0]["auc"], "setup_auc": setup_auc,
                 "n_groups": tried[best][0]["n"], "trained_at": datetime.now().isoformat(timespec="seconds")},
                MODEL_DIR / f"{args.task}.joblib")
    (MODEL_DIR / f"{args.task}_report.md").write_text(text, encoding="utf-8")
    print("\n" + text + f"\nSaved the model and report in {MODEL_DIR}")


if __name__ == "__main__":
    main()
