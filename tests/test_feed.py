import json
from datetime import date

from regtracker import feed
from regtracker.llm import Analysis, Item
from regtracker.pipeline import Entry


def _entry(kind="eu", doc_id="32026R1740", subtitle="CELEX 32026R1740", target="cbam-default-values"):
    a = Analysis(headline="기본값 정정", importance="high", actions=["재계산"],
                 items=[Item(where="Annex I", summary="값 정정", importance="high",
                             impacts=[{"target": target, "reason": "기본값 표"}])])
    return Entry(kind=kind, doc_id=doc_id, title="t", subtitle=subtitle, url="u", status="new", analysis=a)


def test_alert_id_is_stable_per_document_version():
    rev = _entry(kind="revision", doc_id="kr-epd-guideline",
                 subtitle="환경부고시 제2025-127호 (2025-07-30, 일부개정) → 환경부고시 제2025-165호 (2025-10-01, 일부개정)")
    assert feed.alert_id(rev) == "kr-epd-guideline@2025-165"
    assert feed.alert_id(_entry()) == "eu:32026R1740"
    assert feed.alert_id(_entry(kind="notice", doc_id="47536")) == "notice:47536"


def test_update_fills_target_repo_and_keeps_first_detection(tmp_path):
    path = tmp_path / "alerts.json"
    feed.update([_entry()], detected=date(2026, 10, 25), path=path)
    f = feed.update([_entry()], detected=date(2026, 11, 1), path=path)
    (a,) = f["alerts"]
    assert a["detected"] == "2026-10-25"
    assert a["targets"][0]["repo"] == "CBAM_Calculator" and a["targets"][0]["path"] == "see_steel.py"
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == feed.SCHEMA_VERSION


def test_update_skips_unchanged_and_unknown_target_is_kept_blank(tmp_path):
    path = tmp_path / "alerts.json"
    quiet = _entry()
    quiet.status = "unchanged"
    f = feed.update([quiet, _entry(doc_id="X", target="no-such-target")], detected=date(2026, 10, 25), path=path)
    assert [a["id"] for a in f["alerts"]] == ["eu:X"]
    assert f["alerts"][0]["targets"][0]["repo"] == ""
