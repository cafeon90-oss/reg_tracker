"""명령줄 진입점.

  python -m regtracker run [--no-llm] [--no-save]
      추적 대상 전체를 확인하고 reports/YYYY-MM-DD.html 을 만든다.
  python -m regtracker compare <문서 id> <이전 고시번호> <새 고시번호> [--no-llm]
      한 고시의 임의의 두 버전을 비교한다. 예: compare kr-epd-guideline 2024-29 2025-127
  python -m regtracker versions <문서 id>
      국가법령정보센터에서 찾은 버전 목록을 보여 준다.
  python -m regtracker render reports/YYYY-MM-DD.json
      저장된 결과로 HTML만 다시 만든다(API 호출 없음).
"""

from __future__ import annotations

import argparse
import sys

from . import report
from .impact import load_targets
from .llm import Analyzer
from .pipeline import compare_rule, load_sources, run
from .sources import lawgokr


def _rule(doc_id: str) -> dict:
    for r in load_sources().get("admin_rules", []):
        if r["id"] == doc_id:
            return r
    sys.exit(f"config/sources.yaml 에 '{doc_id}' 가 없다.")


def main(argv=None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="regtracker")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--no-llm", action="store_true")
    r.add_argument("--no-save", action="store_true", help="상태 파일(data/seen.json)을 갱신하지 않는다")
    c = sub.add_parser("compare")
    c.add_argument("doc_id")
    c.add_argument("old")
    c.add_argument("new")
    c.add_argument("--no-llm", action="store_true")
    v = sub.add_parser("versions")
    v.add_argument("doc_id")
    g = sub.add_parser("render", help="저장된 JSON 보고서로 HTML만 다시 만든다(API 호출 없음)")
    g.add_argument("json_path")
    a = p.parse_args(argv)

    if a.cmd == "run":
        entries, analyzer = run(use_llm=not a.no_llm, save_state=not a.no_save)
        out = report.write(entries, analyzer)
        print(f"보고서: {out}")
    elif a.cmd == "render":
        from datetime import datetime
        from pathlib import Path
        entries, data = report.load(Path(a.json_path))
        out = report.write(entries, None, title=data["title"], stem=Path(a.json_path).stem,
                           usage=data["usage"], generated=datetime.fromisoformat(data["generated"]))
        print(f"보고서: {out}")
    elif a.cmd == "versions":
        for ver in lawgokr.versions(_rule(a.doc_id)["name"]):
            print(f"{ver.number:>12}  {ver.label}  시행 {ver.effective}")
    elif a.cmd == "compare":
        rule = _rule(a.doc_id)
        by_no = {ver.number: ver for ver in lawgokr.versions(rule["name"])}
        missing = [n for n in (a.old, a.new) if n not in by_no]
        if missing:
            sys.exit(f"버전을 찾지 못했다: {missing}. 'versions {a.doc_id}' 로 목록을 확인할 것.")
        analyzer = None if a.no_llm else Analyzer(load_targets())
        entry = compare_rule(rule, by_no[a.old], by_no[a.new], analyzer)
        out = report.write([entry], analyzer, title=f"{rule['name']} 비교",
                           stem=f"compare_{a.doc_id}_{a.old}_{a.new}")
        print(f"변경 {len(entry.changes)}건 · 보고서: {out}")


if __name__ == "__main__":
    main()
