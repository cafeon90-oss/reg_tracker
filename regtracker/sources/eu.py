"""EU 법령 수집. EUR-Lex 화면은 봇 차단이 있어, EU 출판국의 SPARQL·Cellar를 쓴다.

- SPARQL: 기준 법령(base_celex)을 개정하거나 그에 근거한 법령 목록
- Cellar : CELEX 번호로 영문 본문(XHTML)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from bs4 import BeautifulSoup

from ..http import fetch, fetch_text

SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"
CELLAR = "http://publications.europa.eu/resource/celex/"

_QUERY = """PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?celex ?date ?title WHERE {
 ?base cdm:resource_legal_id_celex "%s"^^<http://www.w3.org/2001/XMLSchema#string> .
 { ?act cdm:resource_legal_amends_resource_legal ?base }
 UNION { ?act cdm:resource_legal_based_on_resource_legal ?base }
 ?act cdm:resource_legal_id_celex ?celex .
 OPTIONAL { ?act cdm:work_date_document ?date }
 OPTIONAL { ?exp cdm:expression_belongs_to_work ?act ;
   cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> ;
   cdm:expression_title ?title }
} ORDER BY DESC(?date) LIMIT 200"""


@dataclass
class Act:
    celex: str
    title: str
    date: date | None

    @property
    def url(self) -> str:
        return f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{self.celex}"

    @property
    def is_legislation(self) -> bool:
        """CELEX 3섹터(규정·지침·결정)만 본문 비교 대상으로 본다. 보고서·공지 등은 목록에만 올린다."""
        return self.celex.startswith("3")


def related_acts(base_celex: str) -> list[Act]:
    raw = fetch(SPARQL, params={"query": _QUERY % base_celex, "format": "application/sparql-results+json"},
                cache=False, timeout=120)
    acts: dict[str, Act] = {}
    for b in json.loads(raw)["results"]["bindings"]:
        celex = b["celex"]["value"]
        d = b.get("date", {}).get("value")
        acts.setdefault(celex, Act(celex=celex, title=b.get("title", {}).get("value", ""),
                                   date=date.fromisoformat(d[:10]) if d else None))
    return sorted(acts.values(), key=lambda a: (a.date or date.min), reverse=True)


def fetch_text_en(celex: str) -> str:
    page = fetch_text(CELLAR + celex, headers={"Accept": "application/xhtml+xml, text/html;q=0.9",
                                               "Accept-Language": "eng"}, timeout=120)
    return BeautifulSoup(page, "html.parser").get_text("\n", strip=True)
