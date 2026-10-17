"""The reading texts. Each takes about 30 seconds to read aloud.

These are placeholders: replace them with your own, but keep an id unchanged once
users have recorded it, because baselines are stored per text id. Avoid digits
(Whisper writes "93" where the text says "ninety-three") and words with two
common spellings (gray/grey), since Whisper picks either one.
"""

TEXTS = {
    "market": {
        "title": "The river market",
        "text": (
            "Every Saturday morning, the small market by the river comes slowly to life. "
            "Farmers unload crates of apples, pears and bright orange pumpkins, while the "
            "baker arranges warm loaves on a wooden table. A man with a bushy beard plays an "
            "old guitar near the bridge, and children stop to listen before running off to "
            "chase the pigeons. By noon the square is crowded and loud. Then, as the "
            "afternoon light fades, the stalls are packed away, and the street becomes "
            "quiet once again."
        ),
    },
    "lighthouse": {
        "title": "The lighthouse keeper",
        "text": (
            "The lighthouse keeper climbed the narrow staircase just before sunset, carrying "
            "a lamp and a heavy wool coat. Outside, the wind was rising, and dark clouds were "
            "gathering over the water. From the top of the tower she could see the fishing "
            "boats hurrying back toward the harbor. She cleaned the great glass lens, checked "
            "the oil, and wrote a short note in her logbook. When the first star appeared, "
            "she lit the beam, and its long white arm began to sweep across the waves."
        ),
    },
    "garden": {
        "title": "A patient garden",
        "text": (
            "My neighbor has the most patient garden I have ever seen. Each spring she plants "
            "tiny seeds in neat rows and waits, without complaint, for weeks of rain and "
            "sunshine to do their quiet work. Soon there are beans climbing a fence, tomatoes "
            "ripening on their vines, and tall yellow sunflowers turning their faces to "
            "follow the sky. She says that a garden teaches you to slow down, to notice small "
            "changes, and to trust that good things often take their time."
        ),
    },
}
