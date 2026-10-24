"""국민참여입법센터(opinion.lawmaking.go.kr) 행정예고 수집.

목록 화면(/gcom/admpp)을 제목 키워드로 검색하고, 새 예고는 상세 화면의 본문을 함께 받는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from bs4 import BeautifulSoup

from ..http import fetch_text

BASE = "https://opinion.lawmaking.go.kr"


@dataclass
class Notice:
    notice_id: str      # 상세 주소의 번호, 예: 47568
    title: str
    rule_type: str      # 고시, 지침, 훈령 …
    agency: str         # 예: 기후에너지환경부 (제2026-939호)
    start: date
    end: date
    url: str
    status: str = ""    # 진행 / 종료
    text: str = ""      # 상세 본문(필요할 때 채움)


def _date(s: str) -> date:
    y, m, d = (int(x) for x in re.findall(r"\d+", s)[:3])
    return date(y, m, d)


def parse_list(page: str) -> list[Notice]:
    soup = BeautifulSoup(page, "html.parser")
    out = []
    for tr in soup.select("table tbody tr"):
        tds = tr.find_all("td")
        a = tr.find("a", href=True)
        if len(tds) < 5 or not a:
            continue
        m = re.search(r"/gcom/admpp/(\d+)", a["href"])
        period = re.findall(r"\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.", tds[4].get_text(" ", strip=True))
        if not m or len(period) < 2:
            continue
        title_cell = tds[1].get_text(" ", strip=True)
        status, _, title = title_cell.partition(" ")
        out.append(Notice(
            notice_id=m[1], title=title.strip(), status=status, rule_type=tds[2].get_text(strip=True),
            agency=tds[3].get_text(" ", strip=True), start=_date(period[0]), end=_date(period[1]),
            url=BASE + a["href"].split("&admRulNm")[0],
        ))
    return out


def search(keyword: str) -> list[Notice]:
    page = fetch_text(BASE + "/gcom/admpp", params={"admRulNm": keyword, "closing": ""}, cache=False)
    return parse_list(page)


def fetch_detail(notice: Notice) -> str:
    """상세 화면에서 예고 본문(개정이유·주요내용)만 추려 돌려준다."""
    soup = BeautifulSoup(fetch_text(notice.url), "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    # 화면 공통 메뉴를 걷어내고 예고 제목부터 첨부자료 안내 전까지만 쓴다.
    i = text.find(notice.title[:20])
    text = text[i:] if i >= 0 else text
    j = text.find("행정규칙안 관련 자료")
    return text[:j] if j >= 0 else text
