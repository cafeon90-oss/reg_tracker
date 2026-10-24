from regtracker.diff import diff_annex, diff_body
from regtracker.parse import annex_segments, split_body

OLD = """환경성적표지 작성지침
[시행 2025. 7. 30.] [환경부고시 제2025-127호, 2025. 7. 30., 일부개정]
제1조(목적)
이 고시는 환경성적 평가방법을 정한다.
제7조(재검토기한)
환경부장관은 2026년 1월 1일을 기준으로 매3년이 되는 시점마다 검토한다.
부      칙
<제2025-127호, 2025. 7. 30.>
제1조(시행일)
이 고시는 발령한 날부터 시행한다.
[별표 1] 환경성적표지 공통지침(일반제품)
"""

NEW = OLD.replace("[시행 2025. 7. 30.] [환경부고시 제2025-127호", "[시행 2025. 10. 7.] [환경부고시 제2025-165호") \
         .replace("환경부장관은", "기후에너지환경부장관은")


def test_split_body_keeps_supplementary_articles_inside_buchik():
    units = {u.key: u for u in split_body(OLD)}
    assert list(units) == ["제1조", "제7조", "부칙 <2025-127>", "별표 목록"]
    assert "제1조(시행일)" in units["부칙 <2025-127>"].text


def test_diff_body_reports_only_changed_article():
    changes = diff_body(OLD, NEW)
    assert [c.where for c in changes] == ["본문 제7조(재검토기한)"]
    assert changes[0].kind == "modified"
    assert "기후에너지환경부장관" in changes[0].new


def test_header_line_change_is_ignored():
    only_header = OLD.replace("[시행 2025. 7. 30.]", "[시행 2025. 8. 1.]")
    assert diff_body(OLD, only_header) == []


def test_numeric_change_is_paired():
    new = OLD.replace("매3년이", "매5년이").replace("2026년", "2027년")
    (c,) = diff_body(OLD, new)
    assert ("2026", "2027") in c.numbers and ("3", "5") in c.numbers


def test_added_and_removed_articles():
    new = OLD.replace("제7조(재검토기한)", "제8조(재검토기한)")
    kinds = {(c.kind, c.where.split("(")[0]) for c in diff_body(OLD, new)}
    assert kinds == {("added", "본문 제8조"), ("removed", "본문 제7조")}


ANNEX = """[별표 5] 개별지침
1. 적용범위
이 지침은 철강 반제품에 적용한다. 할당은 질량 기준으로 한다.
- 12 -
2. 시스템 경계
원료 채취부터 출하까지로 한다.
"""


def test_annex_pdf_reflow_is_not_a_change():
    reflowed = ANNEX.replace("철강 반제품에 적용한다.", "철강 반제품에\n적용한다.").replace("- 12 -", "- 13 -")
    assert diff_annex("[별표 5] 개별지침", ANNEX, reflowed) == []


def test_annex_change_carries_nearest_heading():
    new = ANNEX.replace("질량 기준으로", "경제적 가치 기준으로")
    (c,) = diff_annex("[별표 5] 개별지침", ANNEX, new)
    assert c.where == "별표 5 > 1. 적용범위"
    assert "경제적 가치" in c.new


def test_annex_segments_drop_page_numbers():
    texts = [s for _, s in annex_segments(ANNEX)]
    assert not any(t.strip("- ").isdigit() for t in texts)
