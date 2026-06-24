from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Node:
    """
    Subsystem node — F1 leaf code (e.g. MQA01, AHA10).
    """
    code: str
    description: str
    is_static: bool
    raw_codes: list[str] = field(default_factory=list)
    raw_descriptions: dict[str, str] = field(default_factory=dict)
    raw_present_in: dict[str, list[str]] = field(default_factory=dict)
    present_in: list[str] = field(default_factory=list)


@dataclass
class Section:
    """
    System header — F1 letters-only code (e.g. MQA, MSE).
    Groups related Nodes.
    """
    prefix: str
    label: str
    description: str = ""
    nodes: list[Node] = field(default_factory=list)


@dataclass
class RootNode:
    """
    Main System — F0 group (e.g. =G00n, =T001).
    """
    code: str
    description: str
    instances: list[str]
    count: int
    sections: list[Section] = field(default_factory=list)
