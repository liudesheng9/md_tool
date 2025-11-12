from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass(frozen=True)
class TUIResult:
    selections: List[Path]
    pipeline_tokens: List[str]
    single_outputs: Dict[Path, str]
    multi_bases: Dict[Path, str]
