"""평가 실행기.

  python eval/run_eval.py          # 변경 탐지만 평가(무료, 네트워크만 사용)
  python eval/run_eval.py --llm    # LLM 요약의 중요도·핵심어까지 평가(API 비용 발생)

결과는 eval/results.md 에 표로 남긴다.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from regtracker.impact import load_targets  # noqa: E402
from regtracker.llm import Analyzer  # noqa: E402
from regtracker.pipeline import compare_rule, load_sources  # noqa: E402
from regtracker.sources import lawgokr  # noqa: E402


def location(where: str) -> str:
    """'본문 제7조(재검토기한)' → '본문 제7조', '별표 5 > 2. 경계' → '별표 5', '본문 부칙 <…>' → '본문 부칙'."""
    if where.startswith("본문 부칙"):
        return "본문 부칙"
    if m := re.match(r"본문 (제\d+조(?:의\d+)?)", where):
        return f"본문 {m[1]}"
    return where.split(" > ")[0].strip()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    args = ap.parse_args()

    cases = yaml.safe_load((ROOT / "eval" / "cases.yaml").read_text(encoding="utf-8"))["cases"]
    rules = {r["id"]: r for r in load_sources()["admin_rules"]}
    analyzer = Analyzer(load_targets()) if args.llm else None

    rows, tot_tp, tot_exp, tot_flag, tot_ok = [], 0, 0, 0, 0
    llm_rows = []
    for case in cases:
        rule = rules[case["doc_id"]]
        by_no = {v.number: v for v in lawgokr.versions(rule["name"])}
        entry = compare_rule(rule, by_no[case["old"]], by_no[case["new"]], analyzer)

        flagged = {location(c.where) for c in entry.changes}
        expected = set(case["expect_locations"])
        allowed = expected | set(case.get("allowed_locations", []))
        tp = len(flagged & expected)
        ok = len(flagged & allowed)
        tot_tp, tot_exp, tot_flag, tot_ok = tot_tp + tp, tot_exp + len(expected), tot_flag + len(flagged), tot_ok + ok
        rows.append((case["id"], len(entry.changes), tp, len(expected), ok, len(flagged),
                     sorted(expected - flagged), sorted(flagged - allowed)))

        if analyzer and entry.analysis:
            a = entry.analysis
            blob = a.headline + " " + " ".join(i.summary for i in a.items)
            terms = [t for t in case.get("expect_terms", []) if t in blob]
            llm_rows.append((case["id"], case["expect_importance"], a.importance,
                             a.importance == case["expect_importance"], len(terms), len(case.get("expect_terms", []))))

    lines = [f"# 평가 결과 ({datetime.now():%Y-%m-%d %H:%M})", "",
             "## 변경 탐지 (위치 단위)", "",
             "| 사례 | 변경 건수 | 재현율 | 정밀도 | 놓친 위치 | 오탐 위치 |", "|---|---:|---:|---:|---|---|"]
    for cid, n, tp, ne, ok, nf, miss, extra in rows:
        lines.append(f"| {cid} | {n} | {tp}/{ne} | {ok}/{nf} | {', '.join(miss) or '-'} | {', '.join(extra) or '-'} |")
    lines.append(f"| **합계** | | **{tot_tp}/{tot_exp} ({tot_tp / tot_exp:.0%})** | "
                 f"**{tot_ok}/{tot_flag} ({tot_ok / max(tot_flag, 1):.0%})** | | |")
    if llm_rows:
        lines += ["", "## LLM 요약", "", "| 사례 | 기대 중요도 | 판정 | 일치 | 핵심어 포함 |", "|---|---|---|---|---:|"]
        for cid, exp, got, hit, nt, ntt in llm_rows:
            lines.append(f"| {cid} | {exp} | {got} | {'O' if hit else 'X'} | {nt}/{ntt} |")
        lines.append("")
        lines.append(f"Claude 호출 {analyzer.calls}회, 입력 {analyzer.input_tokens:,} / 출력 {analyzer.output_tokens:,} 토큰")
    report = "\n".join(lines) + "\n"
    (ROOT / "eval" / "results.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
