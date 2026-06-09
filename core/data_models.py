from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Subsystem:
    """
    A group of F1 codes (letters + digits) sharing the same description
    template, differing only in their last digit (e.g. ACA11..19).
    """
    code: str
    description: str
    is_common: bool
    raw_codes: list[str] = field(default_factory=list)
    raw_descriptions: dict[str, str] = field(default_factory=dict)
    present_in: list[str] = field(default_factory=list)


@dataclass
class System:
    """
    F1 section header (letters only, e.g. AHA, MDA).
    Groups related Subsystems together.
    """
    prefix: str
    label: str
    description: str = ""
    subsystems: list[Subsystem] = field(default_factory=list)


@dataclass
class MainSystem:
    """
    Top-level F0 group (e.g. =G00n, =T001).
    """
    code: str
    description: str
    instances: list[str]
    count: int
    systems: list[System] = field(default_factory=list)
