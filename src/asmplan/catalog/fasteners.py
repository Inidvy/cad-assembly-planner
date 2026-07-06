"""DIN/ISO fastener catalog: coarse-pitch table, standard designations, and a
parser that turns a STEP part name into a FastenerSpec.

Pitch is LOOKED UP here, never measured from geometry (STEP threads are usually
cosmetic — see design doc). A name like "ISO 4762 M6x20" -> M6, pitch 1.0 mm,
socket-head cap screw.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from asmplan.schema import PartClass

# ISO 261 metric COARSE pitch, mm, keyed by nominal diameter (mm).
_COARSE_PITCH_MM: dict[float, float] = {
    1.6: 0.35, 2.0: 0.40, 2.5: 0.45, 3.0: 0.50, 3.5: 0.60, 4.0: 0.70,
    5.0: 0.80, 6.0: 1.00, 8.0: 1.25, 10.0: 1.50, 12.0: 1.75, 14.0: 2.00,
    16.0: 2.00, 20.0: 2.50, 24.0: 3.00,
}

# ISO standard number -> part class (the common ones).
_STANDARD_CLASS: dict[str, PartClass] = {
    "4762": PartClass.SCREW,   # socket head cap screw
    "4014": PartClass.BOLT,    # hex bolt (partial thread)
    "4017": PartClass.BOLT,    # hex bolt (full thread)
    "4032": PartClass.NUT,     # hex nut
    "4035": PartClass.NUT,     # thin hex nut
    "7089": PartClass.WASHER,  # plain washer
    "7380": PartClass.SCREW,   # button head screw
}

# Keyword -> part class, checked when no standard number is present.
_KEYWORD_CLASS: list[tuple[str, PartClass]] = [
    ("washer", PartClass.WASHER),
    ("nut", PartClass.NUT),
    ("bolt", PartClass.BOLT),
    ("capscrew", PartClass.SCREW),
    ("cap screw", PartClass.SCREW),
    ("screw", PartClass.SCREW),
]

_METRIC_RE = re.compile(r"\bM(\d+(?:\.\d+)?)(?:\s*[xX]\s*\d+(?:\.\d+)?)?\b")
_STANDARD_RE = re.compile(r"\b(?:ISO|DIN)\s*(\d{3,5})\b", re.IGNORECASE)


def coarse_pitch_mm(diameter_mm: float) -> Optional[float]:
    """Return the ISO coarse pitch for a nominal diameter, or None if unlisted."""
    return _COARSE_PITCH_MM.get(round(diameter_mm, 1))


@dataclass
class FastenerSpec:
    part_class: PartClass
    diameter_mm: Optional[float] = None
    pitch_mm: Optional[float] = None
    standard: Optional[str] = None
    # How much of the identity came from the name (drives classifier confidence).
    matched_standard: bool = False
    matched_metric: bool = False
    matched_keyword: bool = False

    @property
    def is_fastener(self) -> bool:
        return self.part_class.is_fastener


def parse_designation(name: Optional[str]) -> Optional[FastenerSpec]:
    """Parse a STEP part name into a FastenerSpec, or None if it doesn't look
    like a fastener at all."""
    if not name:
        return None
    text = name.strip()
    low = text.lower()

    std_match = _STANDARD_RE.search(text)
    metric_match = _METRIC_RE.search(text)

    part_class: Optional[PartClass] = None
    standard = None
    if std_match:
        standard = std_match.group(1)
        part_class = _STANDARD_CLASS.get(standard)
    if part_class is None:
        for kw, cls in _KEYWORD_CLASS:
            if kw in low:
                part_class = cls
                break
    # A bare metric designation ("M6x20") with no other signal: assume a screw,
    # the most common metric fastener.
    if part_class is None and metric_match:
        part_class = PartClass.SCREW

    if part_class is None:
        return None  # not a fastener

    diameter = pitch = None
    if metric_match:
        diameter = float(metric_match.group(1))
        pitch = coarse_pitch_mm(diameter)

    return FastenerSpec(
        part_class=part_class,
        diameter_mm=diameter,
        pitch_mm=pitch,
        standard=standard,
        matched_standard=std_match is not None and standard in _STANDARD_CLASS,
        matched_metric=metric_match is not None,
        matched_keyword=any(kw in low for kw, _ in _KEYWORD_CLASS),
    )
