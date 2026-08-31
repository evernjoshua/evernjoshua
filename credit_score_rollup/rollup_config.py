"""Credit-band roll-up definitions.

Each group stacks three credit-band tabs (<=600, 601-639, 640+) into a single
combined "_ALL" tab. Source names are matched loosely: case, spaces, and the
common separators used in the band suffixes are ignored, so "Credit Karma
$95 <=600" and "Credit Karma $95<=600" both match.
"""

BANDS = ("<=600", "601-639", "640+")


def _bands(prefix):
    """Sheet names for one campaign prefix across all three credit bands."""
    return [f"{prefix}{band}" for band in BANDS]


# target sheet name -> list of source sheet names, in stacking order
ROLLUPS = {
    "Credit Karma $95_ALL": _bands("Credit Karma $95"),
    "Credit Karma WANDER_ALL": _bands("CK Wander $95"),
    "EXPERIAN WANDER_ALL": _bands("EXPX Wander $95"),
    "Google PQ Paid Search_ALL": _bands("Google $75"),
    "Credit Sesame $75_ALL": _bands("CSOX $75"),
}
