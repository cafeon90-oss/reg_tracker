"""본문과 별표 텍스트를 비교 단위로 나눈다.

- 본문: 조(제N조, 제N조의M) 단위. 부칙은 고시 번호별로 한 단위.
- 별표(PDF): PDF 줄바꿈은 버전마다 달라지므로, 공백을 지우고 문장·번호 단위로 다시 끊은 뒤
  가장 가까운 제목 줄을 위치 정보로 붙인다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ARTICLE_RE = re.compile(r"^(제\d+조(?:의\d+)?)\s*\((.+?)\)")
_SUPPL_RE = re.compile(r"^부\s*칙$")
_SUPPL_NO_RE = re.compile(r"<\s*제?([\w-]+)호")
_ANNEX_LIST_RE = re.compile(r"^\[(별표|부속서|서식)\s*\d+")
_HEADER_RE = re.compile(r"^\[시행 ")


@dataclass
class Unit:
    key: str        # 비교 기준 키. 예: 제7조, 부칙 <2025-165>, 별표 5 > 3.2 시스템 경계
    title: str
    text: str


def split_body(body: str) -> list[Unit]:
    units: list[Unit] = []
    cur: Unit | None = None
    in_suppl = False    # 부칙 안의 제1조(시행일) 등은 본문 조와 섞이지 않게 부칙 단위에 붙인다
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or _HEADER_RE.match(line):
            continue
        if not in_suppl and (m := _ARTICLE_RE.match(line)):
            cur = Unit(key=m[1], title=m[2], text=line)
            units.append(cur)
            continue
        if _SUPPL_RE.match(line):
            in_suppl = True
            no = ""
            if i < len(lines) and (m := _SUPPL_NO_RE.search(lines[i])):
                no = m[1]
                i += 1
            cur = Unit(key=f"부칙 <{no}>", title="부칙", text="")
            units.append(cur)
            continue
        if _ANNEX_LIST_RE.match(line):
            if not units or units[-1].key != "별표 목록":
                cur = Unit(key="별표 목록", title="별표·부속서 목록", text="")
                units.append(cur)
            cur = units[-1]
        if cur is None:
            continue  # 제목·소관부서 등 머리말
        cur.text = f"{cur.text}\n{line}" if cur.text else line
    return _dedupe(units)


def _dedupe(units: list[Unit]) -> list[Unit]:
    """같은 키가 두 번 나오면(부칙 번호가 없는 경우 등) 순번을 붙여 구분한다."""
    seen: dict[str, int] = {}
    for u in units:
        n = seen.get(u.key, 0)
        seen[u.key] = n + 1
        if n:
            u.key = f"{u.key} #{n + 1}"
    return units


# ── 별표(PDF) ───────────────────────────────────────────

_PAGE_NO_RE = re.compile(r"^[-–—\s]*\d+\s*[-–—\s]*$|^\d+\s*/\s*\d+$")
# 끊는 지점: 문장 끝(…다. / …함) 또는 번호 매김 시작(1. / 1.1 / 가. / ① / (1) / ○ / -)
_BREAK_RE = re.compile(r"(?<=다\.)|(?<=함\.)|(?<=[가-힣]\))\s|(?=\s(?:\d+(?:\.\d+)+\.?\s|\d+\.\s|[가-하]\.\s|[①-⑳]|\(\d+\)\s|○|□|■|※))")
_HEADING_RE = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[가-하]\.|제\d+장|\[별표|\[부속서|[IVX]+\.)\s*\S")


def annex_segments(text: str) -> list[tuple[str, str]]:
    """(가장 가까운 제목, 문장) 목록. 공백은 하나로 줄인다."""
    out: list[tuple[str, str]] = []
    heading = ""
    buf: list[str] = []

    def flush() -> None:
        flat = re.sub(r"\s+", " ", " ".join(buf))
        buf.clear()
        for piece in _BREAK_RE.split(flat):
            piece = piece.strip()
            if len(piece) >= 2:
                out.append((heading, piece))

    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or _PAGE_NO_RE.match(ln):
            continue
        # 제목은 PDF에서도 보통 한 줄을 따로 차지하므로, 줄 단위로 먼저 골라낸다.
        if _HEADING_RE.match(ln) and len(ln) <= 60 and not ln.endswith(("다.", "함.")):
            flush()
            heading = re.sub(r"\s+", " ", ln)
            out.append((heading, heading))
        else:
            buf.append(ln)
    flush()
    return out
