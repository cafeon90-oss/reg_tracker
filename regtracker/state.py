"""이미 보고한 항목을 기억하는 작은 상태 파일(data/seen.json). git에 함께 올려 실행 간에 공유한다."""

from __future__ import annotations

import json
from pathlib import Path

from .http import ROOT

STATE_PATH = ROOT / "data" / "seen.json"


class State:
    def __init__(self, path: Path = STATE_PATH):
        self.path = path
        self.data: dict = {}
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))

    def seen(self, bucket: str, key: str) -> bool:
        return key in self.data.get(bucket, [])

    def mark(self, bucket: str, key: str) -> None:
        items = self.data.setdefault(bucket, [])
        if key not in items:
            items.append(key)

    def last(self, doc_id: str) -> str | None:
        """행정규칙별로 마지막으로 보고한 버전 ID."""
        return self.data.get("last_version", {}).get(doc_id)

    def set_last(self, doc_id: str, seq: str) -> None:
        self.data.setdefault("last_version", {})[doc_id] = seq

    def save(self) -> None:
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
