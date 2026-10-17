"""Research screening: how much a recording resembles the condition group of a research dataset.

Not a diagnosis. The models are trained on few speakers, can't tell which condition a
person has, and make mistakes. Train them with `python -m voice_checker.screening.train ...`.
"""
from voice_checker import config

MODEL_DIR = config.MODELS_DIR / "screening"

TASKS = {
    "torgo": {
        "title": "Speech check",
        "pattern": "dysarthria-like speech (slow, slurred or effortful)",
        "dataset": "TORGO: speakers with dysarthria (cerebral palsy or ALS) and control speakers",
        "recording": "reading",
        "credit": ("TORGO database, University of Toronto: Rudzicz, Namasivayam & Wolff (2012), “The TORGO "
                   "database of acoustic and articulatory speech from speakers with dysarthria”, Language "
                   "Resources and Evaluation 46(4). Free for academic (non-profit) use."),
        # Set after validation on 2026-10-17; remove to show results again after retraining on better data.
        "disabled": ("it failed validation: it rated normal readings as highly similar to dysarthric speech, and "
                     "its recording-setup check failed (silence alone separated the groups), so it recognizes "
                     "TORGO's recording sessions rather than speech. TORGO has only 15 speakers."),
    },
    "svd": {
        "title": "Voice check",
        "pattern": "voice-disorder-like voice quality (hoarse, breathy or unstable)",
        "dataset": ("Saarbrücken Voice Database: healthy speakers and people with vocal fold nodules, polyps, "
                    "paralysis, laryngitis or reflux"),
        "recording": "vowel",
        "credit": ("Saarbrücken Voice Database, Manfred Pützer & William J. Barry, former Institute of Phonetics, "
                   "Saarland University (Zenodo 10.5281/zenodo.16874898), licensed CC BY 4.0."),
    },
    "svd_phrase": {
        "title": "Voice check from reading",
        "pattern": "voice-disorder-like voice quality (hoarse, breathy or unstable)",
        "dataset": ("Saarbrücken Voice Database, spoken sentence (German: “Guten Morgen, wie geht es Ihnen?”): "
                    "healthy speakers and people with vocal fold nodules, polyps, paralysis, laryngitis or reflux"),
        "recording": "reading",
        "credit": ("Saarbrücken Voice Database, Manfred Pützer & William J. Barry, former Institute of Phonetics, "
                   "Saarland University (Zenodo 10.5281/zenodo.16874898), licensed CC BY 4.0."),
    },
}
