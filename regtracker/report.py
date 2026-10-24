"""실행 결과를 HTML·JSON 보고서로 쓴다."""

from __future__ import annotations

import html
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .http import ROOT
from .impact import load_targets
from .llm import MODEL

REPORT_DIR = ROOT / "reports"
_IMP = {"high": ("높음", "imp-high"), "medium": ("보통", "imp-mid"), "low": ("낮음", "imp-low")}
_STATUS = {"changed": "개정", "first": "첫 등록", "new": "신규", "unchanged": "변경 없음", "error": "오류"}
_KIND = {"revision": "고시·지침", "notice": "행정예고", "eu": "EU 법령", "error": "수집 오류"}
_ORDER = {"high": 0, "medium": 1, "low": 2, None: 3}

CSS = """
:root{--bg:#f4f6f8;--card:#fff;--text:#1b1f24;--muted:#5f6b7a;--faint:#8a95a3;--line:#e3e6ea;--soft:#f7f8fa;
--accent:#2457c5;--high:#c62828;--high-bg:#fdecea;--mid:#a65b00;--mid-bg:#fff3e0;--low:#2e6b34;--low-bg:#e8f5e9;
--code:#eef1f4;--old-bg:#fdf1f0;--new-bg:#eff8f0}
@media (prefers-color-scheme:dark){:root{--bg:#0f1217;--card:#171b22;--text:#e8ebef;--muted:#a3adb9;--faint:#7c8794;
--line:#2a313b;--soft:#1c2129;--accent:#7aa7ff;--high:#ff8a80;--high-bg:#3a1d1d;--mid:#ffb74d;--mid-bg:#3a2a12;
--low:#81c784;--low-bg:#1b2e1d;--code:#232a33;--old-bg:#2a1a1a;--new-bg:#16261a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:Pretendard,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;
font-weight:500;line-height:1.65;padding:32px 36px;word-break:keep-all;overflow-wrap:anywhere}
h1,h2,h3{font-weight:800;margin:0;line-height:1.35}
h1{font-size:26px;letter-spacing:-.01em}
h2{font-size:18px;margin:32px 0 12px}
h3{font-size:18px;margin-top:10px}
h3 a{color:var(--text);text-decoration:none}
h3 a:hover{color:var(--accent);text-decoration:underline}
a{color:var(--accent)}
.meta{color:var(--muted);font-size:14px;margin-top:6px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:20px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.stat b{display:block;font-size:28px;font-weight:800;line-height:1.2}
.stat span{color:var(--muted);font-size:13px}
.stat.hot b{color:var(--high)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin-bottom:16px}
.card.high{border-left:4px solid var(--high)}
.card.medium{border-left:4px solid var(--mid)}
.card.low{border-left:4px solid var(--line)}
.head{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.badge{display:inline-block;white-space:nowrap;font-size:12px;font-weight:800;line-height:1.5;border-radius:999px;
padding:2px 10px;border:1px solid var(--line);color:var(--muted);background:var(--card)}
.imp-high{background:var(--high-bg);color:var(--high);border-color:transparent}
.imp-mid{background:var(--mid-bg);color:var(--mid);border-color:transparent}
.imp-low{background:var(--low-bg);color:var(--low);border-color:transparent}
.sub{color:var(--muted);font-size:14px;margin:4px 0 14px}
.headline{font-size:16px;font-weight:700;background:var(--soft);border-radius:10px;padding:12px 16px;margin:0 0 14px}
.label{font-size:13px;font-weight:800;color:var(--muted);margin:16px 0 6px}
ol.actions{margin:0;padding-left:22px}
ol.actions li{margin:3px 0}
.items{border-top:1px solid var(--line);margin-top:4px}
.item{display:grid;grid-template-columns:64px 1fr;gap:4px 14px;padding:14px 0;border-bottom:1px solid var(--line)}
.item:last-child{border-bottom:0}
.item .badge{justify-self:start;align-self:start;margin-top:1px}
.where{font-size:13px;font-weight:800;color:var(--muted)}
.item p{margin:2px 0 0}
.impacts{grid-column:2;display:flex;flex-direction:column;gap:6px;margin-top:8px}
.impact{background:var(--soft);border-radius:8px;padding:8px 12px;font-size:14px}
.impact code{font-weight:700;white-space:nowrap;overflow-wrap:normal}
.impact .path{color:var(--faint);font-size:13px;margin-left:6px}
.impact .reason{display:block;color:var(--muted);margin-top:2px}
code{background:var(--code);border-radius:4px;padding:1px 6px;font-size:13px;font-family:'D2Coding',Consolas,monospace}
details{margin-top:14px;border-top:1px solid var(--line);padding-top:12px}
summary{cursor:pointer;color:var(--accent);font-weight:800;font-size:14px}
.diff{padding:10px 0;font-size:13px;border-bottom:1px dashed var(--line)}
.diff .old,.diff .new{border-radius:6px;padding:6px 10px;margin-top:6px}
.diff .old{background:var(--old-bg);color:var(--high)}
.diff .new{background:var(--new-bg);color:var(--low)}
.note{color:var(--muted);font-size:13px;margin-top:12px;white-space:pre-wrap}
.note::before{content:"참고 · ";font-weight:800}
.quiet{color:var(--muted);font-size:14px}
.quiet-list div{padding:6px 0;border-bottom:1px solid var(--line)}
.quiet-list div:last-child{border-bottom:0}
@media (max-width:700px){body{padding:16px}.card{padding:16px}.item{grid-template-columns:1fr}.impacts{grid-column:1}}
"""


def _e(s) -> str:
    return html.escape(str(s or ""))


_CHANGE_KIND = {"added": "추가", "removed": "삭제", "modified": "수정"}


def _badge(imp: str | None, *, prefix: str = "중요도 ") -> str:
    if not imp:
        return ""
    label, cls = _IMP[imp]
    return f'<span class="badge {cls}">{prefix}{label}</span>'


def _impact_html(t: dict, targets) -> str:
    tg = targets.get(t["target"])
    path = f'<span class="path">{_e(tg.repo)}/{_e(tg.path)}</span>' if tg and tg.path not in ("", "-") else (
        f'<span class="path">{_e(tg.repo)}</span>' if tg else "")
    return f'<div class="impact"><code>{_e(t["target"])}</code>{path}<span class="reason">{_e(t["reason"])}</span></div>'


def _entry_html(e, targets) -> str:
    a = e.analysis
    imp = a.importance if a else None
    parts = [f'<div class="card {imp or ""}"><div class="head">{_badge(imp)}'
             f'<span class="badge">{_KIND.get(e.kind, e.kind)}</span>'
             f'<span class="badge">{_STATUS.get(e.status, e.status)}</span></div>',
             "<h3>" + (f'<a href="{_e(e.url)}">{_e(e.title)}</a>' if e.url else _e(e.title)) + "</h3>",
             f'<div class="sub">{_e(e.subtitle)}</div>']
    if a:
        parts.append(f'<div class="headline">{_e(a.headline)}</div>')
        if a.actions:
            parts.append('<div class="label">할 일</div><ol class="actions">'
                         + "".join(f"<li>{_e(x)}</li>" for x in a.actions) + "</ol>")
        items = []
        for it in sorted(a.items, key=lambda i: _ORDER.get(i.importance, 3)):
            impacts = "".join(_impact_html(t, targets) for t in it.impacts)
            items.append(f'<div class="item">{_badge(it.importance, prefix="")}'
                         f'<div><div class="where">{_e(it.where)}</div><p>{_e(it.summary)}</p></div>'
                         + (f'<div class="impacts">{impacts}</div>' if impacts else "") + "</div>")
        if items:
            parts.append(f'<div class="label">위치별 내용</div><div class="items">{"".join(items)}</div>')
    if e.changes:
        numeric = sum(c.numeric for c in e.changes)
        diffs = []
        for c in e.changes[:300]:
            nums = (" · 숫자 " + ", ".join(f"<code>{_e(x)} → {_e(y)}</code>" for x, y in c.numbers[:8])) if c.numbers else ""
            diffs.append(f'<div class="diff"><b>{_e(c.where)}</b> <span class="quiet">{_CHANGE_KIND.get(c.kind, c.kind)}</span>{nums}'
                         + (f'<div class="old">− {_e(c.old[:600])}</div>' if c.old else "")
                         + (f'<div class="new">+ {_e(c.new[:600])}</div>' if c.new else "") + "</div>")
        more = f'<div class="quiet">… 나머지 {len(e.changes) - 300}건은 JSON 보고서에 있다.</div>' if len(e.changes) > 300 else ""
        parts.append(f"<details><summary>원문 변경 {len(e.changes)}건 보기 (숫자 변경 {numeric}건)</summary>"
                     f"{''.join(diffs)}{more}</details>")
    if e.note:
        parts.append(f'<div class="note">{_e(e.note)}</div>')
    parts.append("</div>")
    return "".join(parts)


def usage_text(analyzer) -> str:
    if not analyzer:
        return "LLM 요약 없이 실행"
    return f"Claude 호출 {analyzer.calls}회 · 입력 {analyzer.input_tokens:,} / 출력 {analyzer.output_tokens:,} 토큰 · {MODEL}"


def write(entries, analyzer, *, title: str = "규제·방법론 개정 추적 보고서", stem: str | None = None,
          usage: str | None = None, generated: datetime | None = None) -> Path:
    REPORT_DIR.mkdir(exist_ok=True)
    now = generated or datetime.now()
    stem = stem or now.strftime("%Y-%m-%d")
    usage = usage or usage_text(analyzer)
    targets = {t.id: t for t in load_targets()}

    active = [e for e in entries if e.status != "unchanged"]
    active.sort(key=lambda e: (_ORDER.get(e.analysis.importance if e.analysis else None, 3), e.kind))
    quiet = [e for e in entries if e.status == "unchanged"]
    high = sum(1 for e in active if e.analysis and e.analysis.importance == "high")
    impacted = {t["target"] for e in active if e.analysis for i in e.analysis.items for t in i.impacts}

    body = [
        f"<h1>{_e(title)}</h1>",
        f'<div class="meta">{now:%Y-%m-%d %H:%M} 실행 · {_e(usage)}</div>',
        '<div class="stats">'
        f'<div class="stat"><b>{len(active)}</b><span>새 개정·예고</span></div>'
        f'<div class="stat{" hot" if high else ""}"><b>{high}</b><span>중요도 높음</span></div>'
        f'<div class="stat"><b>{len(impacted)}</b><span>영향받는 코드·데이터</span></div>'
        f'<div class="stat"><b>{len(quiet)}</b><span>변경 없는 추적 문서</span></div></div>',
        "<h2>변경 내역</h2>",
        "".join(_entry_html(e, targets) for e in active) or '<p class="quiet">새로 보고할 변경이 없다.</p>',
    ]
    if quiet:
        body.append("<h2>변경 없음</h2><div class='card quiet-list'>" + "".join(
            f'<div><a href="{_e(e.url)}">{_e(e.title)}</a> <span class="quiet">현행 {_e(e.subtitle)}</span></div>'
            for e in quiet) + "</div>")

    page = (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{_e(title)}</title>'
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">'
            f"<style>{CSS}</style></head><body>{''.join(body)}</body></html>")
    out = REPORT_DIR / f"{stem}.html"
    out.write_text(page, encoding="utf-8")
    data = {"title": title, "generated": now.isoformat(timespec="seconds"), "usage": usage,
            "entries": [asdict(e) for e in entries]}
    (REPORT_DIR / f"{stem}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str),
                                             encoding="utf-8")
    return out


def load(path: Path):
    """write()가 남긴 JSON을 다시 읽는다. 디자인만 고쳐 다시 그릴 때 API를 또 부르지 않으려는 용도."""
    from .diff import Change
    from .llm import Analysis, Item
    from .pipeline import Entry

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = []
    for d in data["entries"]:
        a = d.get("analysis")
        if a:
            a = Analysis(**{**a, "items": [Item(**i) for i in a["items"]]})
        changes = [Change(**{**c, "numbers": [tuple(n) for n in c["numbers"]]}) for c in d.get("changes", [])]
        entries.append(Entry(**{**d, "analysis": a, "changes": changes}))
    return entries, data
