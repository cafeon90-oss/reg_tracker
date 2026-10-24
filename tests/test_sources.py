from datetime import date

from regtracker.impact import Target, candidates, notice_candidates
from regtracker.sources.lawgokr import parse_annex_links, parse_version_list
from regtracker.sources.lawmaking import parse_list

LIST_HTML = """
<a name="liBgcolor8" href="#AJAX" title="환경성적표지 작성지침[시행 2025. 7. 30.] [환경부고시 제2025-127호, 2025. 7. 30., 일부개정]" onclick="javascript:showAdmRulCts('2100000262058', 'Y', '8', 'null');  return false;">
<a name="liBgcolor9" href="#AJAX" title="환경성적표지 작성지침&#13;[시행 2025. 10. 7.] [환경부고시 제2025-165호, 2025. 10. 1., 일부개정]" onclick="javascript:showAdmRulCts('2100000268354', 'Y', '9', 'null');  return false;">
<a name="liBgcolor1" href="#AJAX" title="환경 성적 표지 대상제품과 작성 지침[시행 2015. 10. 19.] [환경부고시 제2015-208호, 2015. 10. 19., 일부개정]" onclick="javascript:showAdmRulCts('2100000072650', 'Y', '1', 'null');  return false;">
"""


def test_parse_version_list_matches_exact_name_and_sorts():
    vs = parse_version_list(LIST_HTML, "환경성적표지 작성지침")
    assert [v.number for v in vs] == ["2025-127", "2025-165"]
    assert vs[-1].seq == "2100000268354"
    assert vs[-1].issued == date(2025, 10, 1) and vs[-1].effective == date(2025, 10, 7)
    assert vs[-1].issuer == "환경부고시" and vs[-1].kind == "일부개정"


def test_parse_annex_links_prefers_second_file_as_pdf():
    body = ('<a href="flDownload.do?flSeq=111&amp;flNm=%5B%EB%B3%84%ED%91%9C+5%5D+%EA%B0%9C%EB%B3%84&amp;bylClsCd=200201">'
            '<a href="flDownload.do?flSeq=222&amp;flNm=%5B%EB%B3%84%ED%91%9C+5%5D+%EA%B0%9C%EB%B3%84&amp;bylClsCd=200201">')
    assert parse_annex_links(body) == [("[별표 5] 개별", "222")]


NOTICE_HTML = """<table><tbody><tr>
<td>1</td><td><a href="/gcom/admpp/47536?announceType=TYPE6&mappingAdmRulSeq=2000000332050&admRulNm=x">진행 환경성적표지 작성지침 일부개정안 행정예고</a></td>
<td>지침</td><td>기후에너지환경부 (제2026-939호)</td><td>2026. 10. 16. ~ 2026. 11. 5.</td><td>4007</td>
</tr></tbody></table>"""


def test_parse_notice_list():
    (n,) = parse_list(NOTICE_HTML)
    assert n.notice_id == "47536"
    assert n.status == "진행" and n.title == "환경성적표지 작성지침 일부개정안 행정예고"
    assert (n.start, n.end) == (date(2026, 10, 16), date(2026, 11, 5))
    assert "admRulNm" not in n.url


def test_impact_candidates_need_doc_and_keyword():
    t = Target(id="x", repo="r", path="p", symbol="-", what="w", docs=["eu-cbam"], keywords=["default value"])
    assert candidates([t], "eu-cbam", "New DEFAULT VALUES for steel") == [t]
    assert candidates([t], "kr-epd-guideline", "default values") == []
    assert candidates([t], "eu-cbam", "nothing relevant") == []


RULES = {"kr-epd-guideline": "환경성적표지 작성지침",
         "kr-ets-mrv": "온실가스 배출권거래제의 배출량 보고 및 인증에 관한 지침"}
STEEL = Target(id="epd-steel", repo="r", path="p", symbol="-", what="w",
               docs=["kr-epd-guideline"], keywords=["철강"])
MRV = Target(id="screener-mrv", repo="carbon_screener", path="data/mrv/", symbol="-", what="w",
             docs=["kr-ets-mrv"], keywords=["검증"], notice_titles=["외부사업", "바이오차"])


def test_notice_linked_through_tracked_rule_name_in_title():
    got = notice_candidates([STEEL, MRV], "환경성적표지 작성지침 일부개정안 행정예고",
                            "개별지침(별표 5) 철강 반제품 개정", RULES)
    assert got == [STEEL]


def test_notice_body_keyword_alone_is_not_enough():
    # 실제 오탐 사례: 자동차 전과정평가 고시의 '검증' 절차가 스크리너 MRV 요건에 붙었다
    title = "자동차 온실가스 전과정평가 방법에 관한 고시 제정안 행정예고"
    assert notice_candidates([STEEL, MRV], title, "단계별 산정방법, 검증·보고 절차를 정한다", RULES) == []


def test_notice_linked_through_notice_titles_or_rule_name():
    body = "모니터링 결과의 검증 절차를 바꾼다"
    assert notice_candidates([MRV], "외부사업 타당성 평가 지침 일부개정안", body, RULES) == [MRV]
    assert notice_candidates([MRV], "온실가스 배출권거래제의 배출량 보고 및 인증에 관한 지침 개정안",
                             body, RULES) == [MRV]
    assert notice_candidates([MRV], "외부사업 타당성 평가 지침 일부개정안", "용어 정비", RULES) == []


def test_llm_impacts_outside_candidates_are_dropped():
    from regtracker.llm import _items_within
    raw = [{"where": "a", "summary": "s", "importance": "high",
            "impacts": [{"target": "screener-mrv", "reason": "r"}, {"target": "epd-steel", "reason": "r"}]}]
    (item,) = _items_within(raw, [STEEL])
    assert [x["target"] for x in item.impacts] == ["epd-steel"]
    (item,) = _items_within(raw, [])
    assert item.impacts == []
