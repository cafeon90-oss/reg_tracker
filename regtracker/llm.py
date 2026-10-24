"""Claude API로 변경 내용을 실무 관점으로 요약하고 영향 대상을 판정한다.

변경이 많으면(예: 별표 전체 개편) 위치별로 묶어 여러 번 나눠 보낸다. 각 변경의 원문은
앞부분만 보내며, 보고서에 그 사실을 적는다.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field

import anthropic

from .diff import Change
from .http import ROOT
from .impact import Target, candidates

MODEL = "claude-opus-5-5"
EXCERPT = 500          # 변경 하나당 보내는 원문 길이(자)
BATCH_CHARS = 60_000   # 한 번에 보내는 분량 상한(자)

SYSTEM = """당신은 한국 온실가스 규제(배출권거래제, 외부사업, 환경성적표지)와 EU CBAM에 밝은 규제 분석가다.
고시·지침 개정 내용을 받아, 실무자가 무엇을 다시 계산하거나 고쳐야 하는지 알려 준다.

원칙:
- 입력에 있는 내용만 근거로 쓴다. 입력에 없는 수치나 조항은 지어내지 않는다.
- 부처명 변경, 띄어쓰기, PDF 줄바꿈 같은 형식 변경은 importance를 "low"로 두고 짧게 적는다.
- 계산식, 계수, 기본값, 시스템 경계, 할당, 적용 대상이 바뀌면 "high"로 둔다.
- 영향 대상은 주어진 후보 목록의 id 중에서만 고르고, 관련이 확실하지 않으면 고르지 않는다.
- 한국어 ~다체 평서문으로 간결하게 쓴다."""

_ITEMS_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "where": {"type": "string", "description": "변경 위치(입력의 위치 표기를 그대로)"},
                    "summary": {"type": "string", "description": "무엇이 어떻게 바뀌었는지 1~3문장"},
                    "importance": {"type": "string", "enum": ["high", "medium", "low"]},
                    "impacts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"target": {"type": "string"}, "reason": {"type": "string"}},
                            "required": ["target", "reason"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["where", "summary", "importance", "impacts"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

_OVERVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "이번 개정의 핵심 한 문장"},
        "importance": {"type": "string", "enum": ["high", "medium", "low"]},
        "actions": {"type": "array", "items": {"type": "string"}, "description": "실무자가 할 일, 최대 5개"},
    },
    "required": ["headline", "importance", "actions"],
    "additionalProperties": False,
}


@dataclass
class Item:
    where: str
    summary: str
    importance: str
    impacts: list[dict] = field(default_factory=list)


@dataclass
class Analysis:
    headline: str
    importance: str
    actions: list[str]
    items: list[Item]
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


def _load_env() -> None:
    """.env의 ANTHROPIC_API_KEY를 환경변수로 올린다(이미 있으면 그대로 둔다)."""
    env = ROOT / ".env"
    if "ANTHROPIC_API_KEY" in os.environ or not env.exists():
        return
    for line in env.read_text(encoding="utf-8-sig").splitlines():
        k, _, v = line.partition("=")
        if k.strip() == "ANTHROPIC_API_KEY" and v.strip():
            os.environ["ANTHROPIC_API_KEY"] = v.strip().strip("'\"")


class Analyzer:
    def __init__(self, targets: list[Target]):
        _load_env()
        self.client = anthropic.Anthropic()
        self.targets = targets
        self.calls = self.input_tokens = self.output_tokens = 0

    def _ask(self, prompt: str, schema: dict) -> dict:
        resp = self.client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        self.calls += 1
        self.input_tokens += resp.usage.input_tokens
        self.output_tokens += resp.usage.output_tokens
        if resp.stop_reason == "refusal":
            raise RuntimeError(f"모델이 요청을 거절했다: {resp.stop_details}")
        if resp.stop_reason == "max_tokens":
            raise RuntimeError("응답이 max_tokens에서 잘렸다. BATCH_CHARS를 줄여 다시 실행할 것.")
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text)

    def _targets_block(self, targets: list[Target]) -> str:
        if not targets:
            return "(이 묶음에 해당하는 후보 없음 — impacts는 빈 배열로 둘 것)"
        return "\n".join(f"- {t.brief()}" for t in targets)

    # ── 행정규칙 개정 ─────────────────────────────────

    def analyze_revision(self, *, doc_id: str, title: str, old_label: str, new_label: str,
                         revision_note: str, changes: list[Change]) -> Analysis:
        groups: dict[str, list[Change]] = defaultdict(list)
        for c in changes:
            groups[c.where].append(c)

        batches, cur, size = [], [], 0
        for where, cs in groups.items():
            block = _group_block(where, cs)
            if cur and size + len(block) > BATCH_CHARS:
                batches.append(cur)
                cur, size = [], 0
            cur.append((where, cs, block))
            size += len(block)
        if cur:
            batches.append(cur)

        items: list[Item] = []
        for batch in batches:
            text = "\n\n".join(b for _, _, b in batch)
            cands = candidates(self.targets, doc_id, text)
            prompt = (
                f"문서: {title}\n비교: {old_label} → {new_label}\n\n"
                f"[공식 제·개정문(개정이유·주요내용)]\n{revision_note[:6000]}\n\n"
                f"[영향 후보]\n{self._targets_block(cands)}\n\n"
                f"[변경 목록] 위치별로 묶었다. 각 원문은 앞 {EXCERPT}자까지만 실었다.\n{text}\n\n"
                "변경 위치마다 items 하나씩 만들어라. 형식 변경만 있는 위치는 하나로 합쳐도 된다."
            )
            out = self._ask(prompt, _ITEMS_SCHEMA)
            items.extend(_items_within(out["items"], cands))

        overview = self._ask(
            f"문서: {title}\n비교: {old_label} → {new_label}\n\n"
            f"[공식 제·개정문]\n{revision_note[:6000]}\n\n"
            "[위치별 분석]\n" + "\n".join(f"- ({i.importance}) {i.where}: {i.summary}" for i in items)
            + "\n\n이번 개정 전체를 한 문장으로 요약하고, 실무자가 할 일을 중요한 순서로 적어라.",
            _OVERVIEW_SCHEMA,
        )
        return Analysis(items=items, **overview)

    # ── 행정예고, EU 법령 ──────────────────────────────

    def analyze_text(self, *, kind: str, title: str, text: str, cands: list[Target]) -> Analysis:
        """본문 하나(행정예고 본문, EU 법령 본문 앞부분)를 요약한다. cands 는 호출하는 쪽이 고른 영향 후보."""
        prompt = (
            f"[{kind}] {title}\n\n[영향 후보]\n{self._targets_block(cands)}\n\n[본문]\n{text}\n\n"
            "핵심 내용을 items로 나눠 적어라(최대 6개). where에는 조항·별표·Annex 등 위치를 쓴다."
        )
        out = self._ask(prompt, _ITEMS_SCHEMA)
        items = _items_within(out["items"], cands)
        overview = self._ask(
            f"[{kind}] {title}\n\n" + "\n".join(f"- ({i.importance}) {i.where}: {i.summary}" for i in items)
            + "\n\n한 문장 요약과 실무자가 할 일을 적어라.",
            _OVERVIEW_SCHEMA,
        )
        return Analysis(items=items, **overview)


def _items_within(raw_items: list[dict], cands: list[Target]) -> list[Item]:
    """LLM이 후보 목록 밖의 대상을 붙였으면 떼어 낸다. 후보가 없으면 영향 대상도 없다."""
    allowed = {t.id for t in cands}
    return [Item(**{**it, "impacts": [x for x in it["impacts"] if x["target"] in allowed]}) for it in raw_items]


def _group_block(where: str, cs: list[Change]) -> str:
    lines = [f"## {where} (변경 {len(cs)}건)"]
    for c in cs[:6]:
        lines.append(f"- [{c.kind}]")
        if c.old:
            lines.append(f"  이전: {c.old[:EXCERPT]}")
        if c.new:
            lines.append(f"  이후: {c.new[:EXCERPT]}")
        if c.numbers:
            lines.append("  숫자 변경: " + ", ".join(f"{a}→{b}" for a, b in c.numbers[:10]))
    if len(cs) > 6:
        lines.append(f"- … 같은 위치의 변경 {len(cs) - 6}건 더 있음")
    return "\n".join(lines)
