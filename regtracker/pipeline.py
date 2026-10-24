"""수집 → 비교 → 요약 → 보고 순서를 묶는다."""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml

from .diff import Change, diff_documents
from .http import ROOT
from .impact import candidates, load_targets, notice_candidates
from .llm import Analysis, Analyzer
from .sources import eu, lawgokr, lawmaking
from .state import State

EU_TEXT_CHARS = 40_000   # EU 법령 본문은 앞부분만 요약에 쓴다(보고서에 표시)


@dataclass
class Entry:
    kind: str                 # revision / notice / eu
    doc_id: str
    title: str
    subtitle: str
    url: str
    status: str               # changed / unchanged / first / new / error
    analysis: Analysis | None = None
    changes: list[Change] = field(default_factory=list)
    note: str = ""            # 보고서에 덧붙일 설명(비교 기준, 잘라 쓴 분량 등)


def load_sources(path: Path = ROOT / "config" / "sources.yaml") -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def compare_rule(rule: dict, old: lawgokr.Version, new: lawgokr.Version,
                 analyzer: Analyzer | None) -> Entry:
    annexes = rule.get("annexes", False)
    old_doc = lawgokr.fetch_document(old, annexes=annexes)
    new_doc = lawgokr.fetch_document(new, annexes=annexes)
    changes = diff_documents(old_doc, new_doc)
    entry = Entry(kind="revision", doc_id=rule["id"], title=rule["name"],
                  subtitle=f"{old.label} → {new.label}", url=new.url, status="changed",
                  changes=changes, note="" if annexes else "본문만 비교했다(별표 제외).")
    if analyzer and changes:
        entry.analysis = analyzer.analyze_revision(
            doc_id=rule["id"], title=rule["name"], old_label=old.label, new_label=new.label,
            revision_note=new_doc.revision_note, changes=changes)
    return entry


def _rule_entry(rule: dict, state: State, analyzer: Analyzer | None) -> Entry:
    vs = lawgokr.versions(rule["name"])
    if not vs:
        return Entry(kind="revision", doc_id=rule["id"], title=rule["name"], subtitle="", url="",
                     status="error", note="국가법령정보센터에서 이 이름의 고시를 찾지 못했다. 이름을 확인할 것.")
    cur = vs[-1]
    last = state.last(rule["id"])
    if last == cur.seq:
        return Entry(kind="revision", doc_id=rule["id"], title=rule["name"], subtitle=cur.label,
                     url=cur.url, status="unchanged")

    by_seq = {v.seq: v for v in vs}
    prev = by_seq.get(last) if last else (vs[-2] if len(vs) >= 2 else None)
    if prev is None:
        # 비교할 직전본이 없다(연혁 목록이 끊긴 경우). 현행본의 제·개정문만 요약한다.
        doc = lawgokr.fetch_document(cur)
        entry = Entry(kind="revision", doc_id=rule["id"], title=rule["name"], subtitle=cur.label,
                      url=cur.url, status="first",
                      note="직전 버전을 찾지 못해 조문 비교 없이 공식 제·개정문만 요약했다. 다음 개정부터 조문을 비교한다.")
        if analyzer:
            entry.analysis = analyzer.analyze_text(
                kind="고시 제·개정문", title=f"{rule['name']} {cur.label}", text=doc.revision_note,
                cands=candidates(analyzer.targets, rule["id"], doc.revision_note))
    else:
        entry = compare_rule(rule, prev, cur, analyzer)
    state.set_last(rule["id"], cur.seq)
    return entry


def _notice_entries(cfg: dict, rule_names: dict[str, str], state: State,
                    analyzer: Analyzer | None) -> list[Entry]:
    since = date.today() - timedelta(days=cfg.get("lookback_days", 120))
    found: dict[str, lawmaking.Notice] = {}
    for kw in cfg["keywords"]:
        for n in lawmaking.search(kw):
            if n.start >= since and not state.seen("notices", n.notice_id):
                found[n.notice_id] = n
    out = []
    for n in sorted(found.values(), key=lambda n: n.start, reverse=True):
        text = lawmaking.fetch_detail(n)
        entry = Entry(kind="notice", doc_id=n.notice_id, title=n.title,
                      subtitle=f"{n.agency} · 의견제출 {n.start:%Y.%m.%d}~{n.end:%Y.%m.%d} · {n.status}",
                      url=n.url, status="new")
        if analyzer:
            entry.analysis = analyzer.analyze_text(
                kind="행정예고", title=n.title, text=text,
                cands=notice_candidates(analyzer.targets, n.title, text, rule_names))
        state.mark("notices", n.notice_id)
        out.append(entry)
    return out


def _eu_entries(act_cfg: dict, state: State, analyzer: Analyzer | None) -> list[Entry]:
    since = date.today() - timedelta(days=act_cfg.get("lookback_days", 120))
    out = []
    for act in eu.related_acts(act_cfg["base_celex"]):
        if not act.date or act.date < since or state.seen("eu", act.celex):
            continue
        entry = Entry(kind="eu", doc_id=act.celex, title=act.title or act.celex,
                      subtitle=f"CELEX {act.celex} · {act.date:%Y-%m-%d} · {act_cfg['name']} 관련",
                      url=act.url, status="new")
        if analyzer:
            if act.is_legislation:
                text = eu.fetch_text_en(act.celex)
                if len(text) > EU_TEXT_CHARS:
                    entry.note = f"본문 {len(text):,}자 중 앞 {EU_TEXT_CHARS:,}자를 기준으로 요약했다."
                    text = text[:EU_TEXT_CHARS]
            else:
                text = act.title
                entry.note = "법령이 아닌 문서(보고서·공지)라 제목만으로 요약했다."
            entry.analysis = analyzer.analyze_text(
                kind="EU 법령", title=act.title, text=text,
                cands=candidates(analyzer.targets, act_cfg["id"], act.title + "\n" + text))
        state.mark("eu", act.celex)
        out.append(entry)
    return out


def run(*, use_llm: bool = True, save_state: bool = True) -> tuple[list[Entry], Analyzer | None]:
    cfg = load_sources()
    state = State()
    analyzer = Analyzer(load_targets()) if use_llm else None
    entries: list[Entry] = []

    def guarded(label: str, fn):
        try:
            res = fn()
            entries.extend(res if isinstance(res, list) else [res])
        except Exception as e:  # 한 출처가 실패해도 나머지는 보고한다
            entries.append(Entry(kind="error", doc_id=label, title=label, subtitle="", url="",
                                 status="error", note=f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"))

    for rule in cfg.get("admin_rules", []):
        guarded(rule["id"], lambda r=rule: _rule_entry(r, state, analyzer))
    if "notices" in cfg:
        rule_names = {r["id"]: r["name"] for r in cfg.get("admin_rules", [])}
        guarded("notices", lambda: _notice_entries(cfg["notices"], rule_names, state, analyzer))
    for act in cfg.get("eu_acts", []):
        guarded(act["id"], lambda a=act: _eu_entries(a, state, analyzer))

    if save_state:
        state.save()
    return entries, analyzer
