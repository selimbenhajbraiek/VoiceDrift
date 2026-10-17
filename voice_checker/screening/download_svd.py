"""Download the Saarbrücken Voice Database vowel /a/ (normal pitch) recordings as WAV files.

The official full dataset is on Zenodo (CC BY 4.0, credit: Pützer & Barry, Saarland University):
https://zenodo.org/records/16874898. Each condition is one big zip; instead of downloading
whole zips, this reads each zip's index over HTTP range requests and fetches only the
<session>-a_n.nsp files (about 150 KB each), plus the zip's overview.csv (speaker ids).

Run:  python -m voice_checker.screening.download_svd E:/VoiceDrift-data/svd            (vowel /a/, normal pitch)
      python -m voice_checker.screening.download_svd E:/VoiceDrift-data/svd --phrase   (the spoken sentence)
"""
import io
import struct
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests
import soundfile as sf

from voice_checker import config

BASE = "https://zenodo.org/records/16874898/files/"
CATEGORIES = {  # Zenodo zip -> output folder (the user's target conditions, plus healthy speakers)
    "healthy.zip": "healthy",
    "Phonationskno\u0308tchen.zip": "nodules",
    "Stimmlippenpolyp.zip": "polyp",
    "Rekurrensparese.zip": "vocal_fold_paralysis",
    "Laryngitis.zip": "laryngitis",
    "GERD.zip": "reflux",
}
WORKERS = 1        # Zenodo rate-limits guests, so one paced connection is fastest overall
MIN_INTERVAL_S = 1.0


class HttpFile(io.RawIOBase):
    """A read-only, seekable file over HTTP range requests (enough for zipfile)."""

    def __init__(self, url, session):
        self.url, self.session, self.pos = url, session, 0
        self.size = int(session.head(url, allow_redirects=True, timeout=60).headers["Content-Length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        self.pos = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence] + offset
        return self.pos

    def readinto(self, buffer):
        if self.pos >= self.size:
            return 0
        end = min(self.pos + len(buffer), self.size) - 1
        for attempt in range(10):
            time.sleep(MIN_INTERVAL_S)  # stay under the guest rate limit
            r = self.session.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"}, timeout=120)
            if r.status_code == 206:
                break
            wait = int(r.headers.get("Retry-After", 0)) or min(2**attempt * 5, 300)
            print(f"  HTTP {r.status_code}, waiting {wait} s", flush=True)
            time.sleep(wait)
        else:
            raise OSError(f"range request failed with HTTP {r.status_code}")
        buffer[: len(r.content)] = r.content
        self.pos += len(r.content)
        return len(r.content)


def open_zip(name, session):
    """Open a Zenodo zip remotely; a 512 KB buffer fetches most recordings in one request."""
    return zipfile.ZipFile(io.BufferedReader(HttpFile(BASE + requests.utils.quote(name) + "?download=1", session), 512 * 1024))


def read_nsp(data):
    """Decode a Kay/CSL .nsp file into (int16 samples, sample rate)."""
    if data[:8] != b"FORMDS16":
        raise ValueError("not an NSP file")
    pos, rate, samples = 12, None, None
    while pos + 8 <= len(data):
        chunk, size = data[pos : pos + 4], struct.unpack_from("<I", data, pos + 4)[0]
        if chunk in (b"HEDR", b"HDR8"):
            rate = struct.unpack_from("<i", data, pos + 8 + 20)[0]
        elif chunk in (b"SDA_", b"SDAB"):
            samples = np.frombuffer(data, "<i2", count=size // 2, offset=pos + 8)
        pos += 8 + size + (size % 2)
    if rate is None or samples is None:
        raise ValueError("NSP file without header or audio")
    return samples, rate


def fetch(name, members, out_dir):
    """Download and convert some members of one zip (one worker, its own connection)."""
    session = requests.Session()
    with open_zip(name, session) as z:
        for member in members:
            target = out_dir / (Path(member).stem + ".wav")
            if not target.exists():
                samples, rate = read_nsp(z.read(member))
                sf.write(target, samples, rate, subtype="PCM_16")


def download_category(name, folder, root, suffix="-a_n.nsp"):
    """All recordings ending in `suffix` of one condition, plus its overview.csv, into root/folder/."""
    out_dir = Path(root) / folder
    out_dir.mkdir(parents=True, exist_ok=True)
    with open_zip(name, requests.Session()) as z:
        names = z.namelist()
        if "overview.csv" in names:
            (out_dir / "overview.csv").write_bytes(z.read("overview.csv"))
    members = [m for m in names if m.endswith(suffix)]
    todo = [m for m in members if not (out_dir / (Path(m).stem + ".wav")).exists()]
    print(f"{folder}: {len(members)} recordings, {len(todo)} to download", flush=True)
    chunks = [todo[i::WORKERS] for i in range(WORKERS)]
    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(lambda c: fetch(name, c, out_dir), [c for c in chunks if c]))
    print(f"{folder}: done ({len(list(out_dir.glob('*' + Path(suffix).stem + '.wav')))} WAV files)", flush=True)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = args[0] if args else "data/svd"
    suffix = "-phrase.nsp" if "--phrase" in sys.argv else "-a_n.nsp"
    start = time.time()
    for name, folder in CATEGORIES.items():
        download_category(name, folder, root, suffix)
    print(f"All done in {(time.time() - start) / 60:.1f} min -> {root}")
