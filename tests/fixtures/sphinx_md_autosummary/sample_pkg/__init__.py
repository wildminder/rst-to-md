"""A tiny sample package used to exercise autosummary source enrichment.

The functions mirror the librosa ``beat`` API so the enrichment output matches
the user's expected shape (all-optional signatures rendered as ``(*[, ...])``).
"""


def beat_track(y=None, sr=None, onset_envelope=None):
    """Dynamic programming beat tracker.

    Finds the beat times in an audio signal using a dynamic-programming
    approach and returns the estimated beat positions.
    """
    return []


def plp(y=None, sr=None, hop_length=None):
    """Predominant local pulse (PLP) estimation.

    Estimates the local pulse of an audio signal from its onset
    tempogram and returns the PLP envelope.
    """
    return []
