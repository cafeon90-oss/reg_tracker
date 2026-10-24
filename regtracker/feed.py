"""다른 저장소가 읽는 알림 피드(feed/alerts.json).

형식은 feed/SCHEMA.md 에 적고, 바꿀 때는 SCHEMA_VERSION 을 올린다.
알림은 실행마다 덮어쓰지 않고 쌓는다. 읽는 쪽이 자기 저장소의 확인 완료 목록(ack)으로 걸러 낸다.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

from .http import ROOT
from .impact import load_targets

SCHEMA_VERSION = 1
FEED_PATH = ROOT / "feed" / "alerts.json"
SOURCE = "https://github.com/cafeon90-oss/reg_tracker"
KEEP_DAYS = 730   # 이보다 오래된 알림은 피드에서 뺀다


def alert_id(e) -> str:
    """알림 id. 같은 개정·예고·법령이면 다시 실행해도 같은 값이 나와야 한다."""
    if e.kind == "revision":
        numbers = re.findall(r"제([\w-]+)호", e.subtitle)
        return f"{e.doc_id}@{numbers[-1] if numbers else e.subtitle}"
    return f"{e.kind}:{e.doc_id}"


def _alert(e, detected: date, targets: dict) -> dict:
    a = e.analysis
    hits = []
    for it in a.items:
        for t in it.impacts:
            tg = targets.get(t["target"])
            hits.append({
                "target": t["target"],
                "repo": tg.repo if tg else "",
                "path": tg.path if tg else "",
                "symbol": tg.symbol if tg else "",
                "importance": it.importance,
                "where": it.where,
                "summary": it.summary,
                "reason": t["reason"],
            })
    return {
        "id": alert_id(e),
        "kind": e.kind,
        "source_doc": e.doc_id,
        "title": e.title,
        "subtitle": e.subtitle,
        "url": e.url,
        "detected": detected.isoformat(),
        "importance": a.importance,
        "headline": a.headline,
        "actions": a.actions,
        "targets": hits,
        "note": e.note,
    }


def update(entries, detected: date | None = None, path: Path = FEED_PATH) -> dict:
    """이번 실행의 요약 결과를 피드에 합친다. 같은 id가 있으면 새 내용으로 바꾸되 처음 감지한 날은 유지한다."""
    detected = detected or date.today()
    targets = {t.id: t for t in load_targets()}
    feed = load(path)
    by_id = {a["id"]: a for a in feed["alerts"]}
    for e in entries:
        if e.status in ("unchanged", "error") or not e.analysis:
            continue
        new = _alert(e, detected, targets)
        if old := by_id.get(new["id"]):
            new["detected"] = old["detected"]
        by_id[new["id"]] = new

    cutoff = detected.toordinal() - KEEP_DAYS
    alerts = [a for a in by_id.values() if date.fromisoformat(a["detected"]).toordinal() >= cutoff]
    alerts.sort(key=lambda a: (a["detected"], a["id"]), reverse=True)
    feed = {"schema_version": SCHEMA_VERSION, "generated": datetime.now().isoformat(timespec="seconds"),
            "source": SOURCE, "alerts": alerts}
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(feed, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return feed


def load(path: Path = FEED_PATH) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema_version": SCHEMA_VERSION, "generated": "", "source": SOURCE, "alerts": []}
