"""Voice signature: a 192-dim SpeechBrain ECAPA speaker embedding.

Test:  python -m features.embedding path/to/clip.wav [other_clip.wav]
"""
from functools import lru_cache

import numpy as np
import torch
from speechbrain.inference.speaker import EncoderClassifier
from speechbrain.utils.fetching import LocalStrategy

import config
from features.pauses import speech_segments


@lru_cache(maxsize=None)
def get_model():
    """Download (first run only) and load the ECAPA encoder on CPU."""
    return EncoderClassifier.from_hparams(
        source=config.ECAPA_MODEL,
        savedir=str(config.MODELS_DIR / "ecapa"),
        run_opts={"device": "cpu"},
        local_strategy=LocalStrategy.COPY,  # Windows: copy files instead of symlinking
    )


def speech_only(wav):
    """Concatenate the VAD speech segments, dropping pauses and background noise."""
    sr = config.SAMPLE_RATE
    parts = [wav[int(start * sr) : int(end * sr)] for start, end in speech_segments(wav)]
    return np.concatenate(parts) if parts else wav


def embed(wav):
    """Return the L2-normalized 192-dim embedding of the speech in a 16 kHz mono clip.

    Only speech frames are used: in tests, adding faint background hiss moved the
    full-clip embedding 5x further than the speech-only one.
    """
    with torch.no_grad():
        emb = get_model().encode_batch(torch.from_numpy(speech_only(wav)).unsqueeze(0))
    emb = emb.squeeze().numpy()
    return emb / np.linalg.norm(emb)


if __name__ == "__main__":
    import sys

    from audio.quality import load_audio

    vecs = [embed(load_audio(path)) for path in sys.argv[1:3]]
    print(f"dim={vecs[0].shape[0]}  norm={np.linalg.norm(vecs[0]):.3f}  first 5: {np.round(vecs[0][:5], 4)}")
    if len(vecs) == 2:
        print(f"cosine similarity between the two clips: {float(vecs[0] @ vecs[1]):.3f}")
