from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class F1Leaf:
    """
    A group of F1 codes sharing the same description template,
    differing only in their last digit (e.g. ACA11..19).
    """

    # Display code: single "=ACA01" or range "=ACA11..19"
    code: str

    # Generalised description with numeric parts replaced where they vary
    description: str

    # True if present in ALL F0 instances of the parent group
    is_common: bool

    # Raw codes that make up this leaf group (e.g. ["ACA11","ACA12",...,"ACA19"])
    raw_codes: list[str] = field(default_factory=list)

    # F0 instances this leaf is present in (only meaningful when is_common=False)
    present_in: list[str] = field(default_factory=list)


@dataclass
class F1Section:
    """
    Group of F1 leaves sharing the same 3-letter prefix (e.g. MQA, BFA).
    """

    prefix: str
    label: str
    description: str = ""
    leaves: list[F1Leaf] = field(default_factory=list)


@dataclass
class F0Group:
    """
    One generalised F0 system group (e.g. =G00n).
    """

    code: str
    description: str
    instances: list[str]
    count: int
    f1_sections: list[F1Section] = field(default_factory=list)
