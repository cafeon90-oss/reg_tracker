"""국가법령정보센터(law.go.kr) 행정규칙 수집.

Open API 인증키 없이, 사이트 화면이 내부적으로 부르는 엔드포인트를 그대로 쓴다.
- admRulScListR.do : 이름 검색(연혁 포함) → 버전 목록
- admRulLsInfoR.do : 특정 버전의 본문
- admRulRvsInfoR.do: 제·개정문(개정이유와 주요내용)
- flDownload.do    : 별표·부속서 첨부파일
"""

from __future__ import annotations

import html
import io
import re
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import quote, unquote_plus

from bs4 import BeautifulSoup
from pypdf import PdfReader

from ..http import fetch, fetch_text

BASE = "https://www.law.go.kr/LSW/"
_BODY_PARAMS = {"joTpYn": "Y", "languageType": "Ko", "chrClsCd": "010202"}

# title="환경성적표지 작성지침[시행 2025. 10. 7.] [환경부고시 제2025-165호, 2025. 10. 1., 일부개정]"
#   onclick="javascript:showAdmRulCts('2100000268354', ...
_ITEM_RE = re.compile(
    r'title="(?P<name>[^"\[]+)\[시행 (?P<eff>[\d. ]+)\]\s*\[(?P<issuer>[^"\]]*?)\s*제(?P<no>[\w-]+)호,\s*'
    r'(?P<issued>[\d. ]+),\s*(?P<kind>[^"\]]+)\]"\s*onclick="javascript:showAdmRulCts\(\'(?P<seq>\d+)\''
)
_ANNEX_RE = re.compile(r"flDownload\.do\?flSeq=(\d+)&flNm=([^&\"']+)")


@dataclass
class Version:
    seq: str            # 사이트 내부 버전 ID (admRulSeq)
    name: str
    number: str         # 고시 번호, 예: 2025-165
    issuer: str         # 예: 환경부고시
    issued: date        # 발령일
    effective: date     # 시행일
    kind: str           # 일부개정, 전부개정, 제정 …

    @property
    def label(self) -> str:
        return f"{self.issuer} 제{self.number}호 ({self.issued.isoformat()}, {self.kind})"

    @property
    def url(self) -> str:
        return f"{BASE}admRulLsInfoP.do?admRulSeq={self.seq}"


@dataclass
class Annex:
    title: str          # 예: [별표 5] 환경성적표지 제품군별 작성지침(개별지침)
    file_seq: str
    text: str = ""


@dataclass
class Document:
    version: Version
    body: str                                   # 본문(조문)
    revision_note: str                          # 제·개정문(개정이유·주요내용)
    annexes: list[Annex] = field(default_factory=list)


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _date(s: str) -> date:
    y, m, d = (int(x) for x in re.findall(r"\d+", s)[:3])
    return date(y, m, d)


def parse_version_list(page: str, name: str) -> list[Version]:
    """검색 결과 HTML에서 이름이 정확히 같은 버전만 골라 발령일 순으로 돌려준다."""
    out = []
    for m in _ITEM_RE.finditer(page):
        if _norm(html.unescape(m["name"])) != _norm(name):
            continue
        out.append(Version(
            seq=m["seq"], name=html.unescape(m["name"]).strip(), number=m["no"],
            issuer=m["issuer"].strip(), issued=_date(m["issued"]), effective=_date(m["eff"]),
            kind=m["kind"].strip(),
        ))
    out.sort(key=lambda v: (v.issued, v.seq))
    return out


def list_versions(name: str) -> list[Version]:
    data = {
        "q": name, "query": name, "section": "admRulNm", "outmax": "100", "pg": "1",
        "p6": "1,2,3",  # 1:연혁 2:시행예정 3:현행
        "p5": ",".join(f"2004{i:02d}" for i in range(1, 13)),  # 제·개정 구분 전체(타법개정 포함)
        "admType": "N", "fsort": "10,41,21,31",
    }
    page = fetch_text(BASE + "admRulScListR.do?menuId=5&subMenuId=41&tabMenuId=183",
                      method="POST", data=data, cache=False)
    return parse_version_list(page, name)


# 본문 첫머리: [시행 2025. 10. 7.] [환경부고시 제2025-165호, 2025. 10. 1., 일부개정]
_HEADER_RE = re.compile(r"\[시행 (?P<eff>[\d. ]+)\]\s*\[(?P<issuer>\S+?)\s*제(?P<no>[\w-]+)호,\s*"
                        r"(?P<issued>[\d. ]+),\s*(?P<kind>[^\]]+)\]")


def current_version(name: str) -> Version | None:
    """이름 주소(/행정규칙/이름)로 현행본을 찾는다. 여러 부처 공동 고시처럼
    검색 목록에 안 잡히는 경우가 있어, 현행본은 이 경로를 기준으로 삼는다."""
    page = fetch_text("https://www.law.go.kr" + quote("/행정규칙/" + _norm(name)), cache=False)
    m = re.search(r"admRulSeq=(\d{10,})", page)
    if not m:
        return None
    _, body = _post_text("admRulLsInfoR.do", m[1])
    h = _HEADER_RE.search(body[:500])
    if not h:
        return None
    return Version(seq=m[1], name=name, number=h["no"], issuer=h["issuer"], issued=_date(h["issued"]),
                   effective=_date(h["eff"]), kind=h["kind"].strip())


def versions(name: str) -> list[Version]:
    """연혁 목록에 현행본을 합쳐 발령일 순으로 돌려준다."""
    found = {v.seq: v for v in list_versions(name)}
    cur = current_version(name)
    if cur and cur.seq not in found:
        found[cur.seq] = cur
    return sorted(found.values(), key=lambda v: (v.issued, v.seq))


def _post_text(endpoint: str, seq: str) -> tuple[str, str]:
    page = fetch_text(BASE + endpoint, method="POST", data={"admRulSeq": seq, **_BODY_PARAMS})
    return page, BeautifulSoup(page, "html.parser").get_text("\n", strip=True)


def _pdf_text(raw: bytes) -> str:
    reader = PdfReader(io.BytesIO(raw))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_annex_links(body_html: str) -> list[tuple[str, str]]:
    """(제목, PDF 파일 ID) 목록. 같은 제목이 HWP·PDF 순으로 두 번 나오므로 두 번째를 PDF로 본다."""
    by_title: dict[str, list[str]] = {}
    for seq, raw_name in _ANNEX_RE.findall(html.unescape(body_html)):
        by_title.setdefault(unquote_plus(raw_name).strip(), []).append(seq)
    return [(t, seqs[-1]) for t, seqs in by_title.items()]


def fetch_document(version: Version, *, annexes: bool = False) -> Document:
    body_html, body = _post_text("admRulLsInfoR.do", version.seq)
    _, note = _post_text("admRulRvsInfoR.do", version.seq)
    doc = Document(version=version, body=body, revision_note=note)
    if annexes:
        for title, file_seq in parse_annex_links(body_html):
            raw = fetch(BASE + "flDownload.do", params={"flSeq": file_seq})
            text = _pdf_text(raw) if raw[:4] == b"%PDF" else ""
            doc.annexes.append(Annex(title=title, file_seq=file_seq, text=text))
    return doc
