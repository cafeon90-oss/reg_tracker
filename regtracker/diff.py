"""두 버전을 비교해 바뀐 단위를 뽑는다. 숫자가 바뀐 경우는 따로 표시한다."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from .parse import Unit, annex_segments, split_body

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)*(?:\s*%)?")


@dataclass
class Change:
    where: str              # 예: 본문 제7조, 별표 5 > 2.3 할당
    kind: str               # added / removed / modified
    old: str = ""
    new: str = ""
    numbers: list[tuple[str, str]] = field(default_factory=list)   # (이전 숫자, 새 숫자)

    @property
    def numeric(self) -> bool:
        return bool(self.numbers)


def _numbers_changed(old: str, new: str) -> list[tuple[str, str]]:
    """숫자만 다르고 나머지 문구가 같은 위치를 찾아 짝지어 준다."""
    a, b = _NUM_RE.findall(old), _NUM_RE.findall(new)
    if not a or not b:
        return []
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    pairs = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "replace" and (i2 - i1) == (j2 - j1):
            pairs.extend(zip(a[i1:i2], b[j1:j2]))
    return pairs


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def diff_body(old: str, new: str) -> list[Change]:
    a = {u.key: u for u in split_body(old)}
    b = {u.key: u for u in split_body(new)}
    changes = []
    for key, u in b.items():
        if key not in a:
            changes.append(Change(where=f"본문 {key}({u.title})", kind="added", new=u.text))
        elif _squash(a[key].text) != _squash(u.text):
            changes.append(_modified(f"본문 {key}({u.title})", a[key].text, u.text))
    for key, u in a.items():
        if key not in b:
            changes.append(Change(where=f"본문 {key}({u.title})", kind="removed", old=u.text))
    return changes


def _modified(where: str, old: str, new: str) -> Change:
    """조 전체 대신 바뀐 줄만 남겨 읽기 쉽게 한다."""
    ol, nl = old.splitlines(), new.splitlines()
    sm = difflib.SequenceMatcher(a=[_squash(x) for x in ol], b=[_squash(x) for x in nl], autojunk=False)
    o, n = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != "equal":
            o.extend(ol[i1:i2])
            n.extend(nl[j1:j2])
    old_part, new_part = "\n".join(o), "\n".join(n)
    return Change(where=where, kind="modified", old=old_part, new=new_part,
                  numbers=_numbers_changed(old_part, new_part))


def diff_annex(title: str, old: str, new: str) -> list[Change]:
    """별표 하나를 문장 단위로 비교하고, 붙어 있는 변경은 한 덩어리로 묶는다."""
    a, b = annex_segments(old), annex_segments(new)
    sm = difflib.SequenceMatcher(a=[_squash(s) for _, s in a], b=[_squash(s) for _, s in b], autojunk=False)
    short = re.sub(r"^\[([^\]]+)\].*", r"\1", title)
    changes = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        heading = (b[j1][0] if j1 < len(b) else "") or (a[i1][0] if i1 < len(a) else "")
        old_part = " ".join(s for _, s in a[i1:i2])
        new_part = " ".join(s for _, s in b[j1:j2])
        if _squash(old_part) == _squash(new_part):
            continue  # PDF 줄바꿈만 다른 경우
        kind = {"insert": "added", "delete": "removed"}.get(op, "modified")
        changes.append(Change(where=f"{short} > {heading}" if heading else short, kind=kind,
                              old=old_part, new=new_part, numbers=_numbers_changed(old_part, new_part)))
    return changes


def diff_documents(old_doc, new_doc) -> list[Change]:
    """lawgokr.Document 두 개를 비교한다. 별표는 제목의 번호(별표 5, 부속서 2)로 짝짓는다."""
    changes = diff_body(old_doc.body, new_doc.body)
    key = lambda t: re.sub(r"\s+", "", re.match(r"\[[^\]]+\]", t)[0]) if re.match(r"\[[^\]]+\]", t) else t
    old_annex = {key(x.title): x for x in old_doc.annexes}
    for ax in new_doc.annexes:
        prev = old_annex.pop(key(ax.title), None)
        if prev is None:
            changes.append(Change(where=ax.title, kind="added", new=ax.text[:2000]))
        elif _squash(prev.text) != _squash(ax.text):
            changes.extend(diff_annex(ax.title, prev.text, ax.text))
    for ax in old_annex.values():
        changes.append(Change(where=ax.title, kind="removed", old=ax.text[:2000]))
    return changes
