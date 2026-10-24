from datetime import date

from regtracker.impact import Target, candidates
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
    assert candidates([t], None, "default values") == [t]
