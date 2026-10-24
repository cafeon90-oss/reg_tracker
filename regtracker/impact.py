"""영향 연결표(config/impact_map.yaml)에서 변경별 후보 대상을 고른다. 최종 판단은 LLM이 한다."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .http import ROOT


@dataclass
class Target:
    id: str
    repo: str
    path: str
    symbol: str
    what: str
    docs: list[str]
    keywords: list[str]

    def brief(self) -> str:
        loc = f"{self.repo}/{self.path}" + (f" ({self.symbol})" if self.symbol not in ("", "-") else "")
        return f"{self.id}: {self.what} — {loc}"


def load_targets(path: Path = ROOT / "config" / "impact_map.yaml") -> list[Target]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Target(**t) for t in data["targets"]]


def candidates(targets: list[Target], doc_id: str | None, text: str) -> list[Target]:
    """출처 문서가 맞고(doc_id가 None이면 문서 조건은 생략) 키워드가 하나라도 들어간 대상."""
    low = text.lower()
    return [t for t in targets
            if (doc_id is None or doc_id in t.docs) and any(k.lower() in low for k in t.keywords)]
