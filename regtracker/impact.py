"""영향 연결표(config/impact_map.yaml)에서 변경별 후보 대상을 고른다. 최종 판단은 LLM이 하되,
LLM은 여기서 고른 후보 밖의 대상을 붙일 수 없다(llm.Analyzer 가 걸러 낸다)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
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
    notice_titles: list[str] = field(default_factory=list)

    def brief(self) -> str:
        loc = f"{self.repo}/{self.path}" + (f" ({self.symbol})" if self.symbol not in ("", "-") else "")
        return f"{self.id}: {self.what} — {loc}"


def load_targets(path: Path = ROOT / "config" / "impact_map.yaml") -> list[Target]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Target(**t) for t in data["targets"]]


def _has_keyword(t: Target, text: str) -> bool:
    low = text.lower()
    return any(k.lower() in low for k in t.keywords)


def candidates(targets: list[Target], doc_id: str, text: str) -> list[Target]:
    """출처 문서가 연결표의 docs 에 있고, 바뀐 내용에 키워드가 하나라도 들어간 대상."""
    return [t for t in targets if doc_id in t.docs and _has_keyword(t, text)]


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def notice_candidates(targets: list[Target], title: str, text: str,
                      rule_names: dict[str, str]) -> list[Target]:
    """행정예고는 출처 문서가 정해져 있지 않아 본문 키워드만으로는 오탐이 많다.
    그래서 제목이 먼저 대상과 이어져야 한다: 제목에 추적 중인 고시 이름(rule_names: 문서 id → 이름)이
    들어 있고 그 문서가 대상의 docs 에 있거나, 제목에 대상의 notice_titles 중 하나가 들어 있어야 한다.
    그다음 본문에 대상 키워드가 있어야 후보가 된다."""
    t_title = _squash(title)
    named = {doc for doc, name in rule_names.items() if _squash(name) in t_title}
    out = []
    for t in targets:
        by_doc = bool(named & set(t.docs))
        by_title = any(_squash(k) in t_title for k in t.notice_titles)
        if (by_doc or by_title) and _has_keyword(t, title + "\n" + text):
            out.append(t)
    return out
