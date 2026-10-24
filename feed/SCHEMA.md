# feed/alerts.json 형식 (schema_version 1)

다른 저장소가 규정 변경 알림을 읽는 파일이다. 주소:

```
https://raw.githubusercontent.com/cafeon90-oss/reg_tracker/main/feed/alerts.json
```

`python -m regtracker run`이 요약까지 마치면 갱신된다. 알림은 실행마다 덮어쓰지 않고 쌓이며, 2년이 지난 알림만 빠진다.

## 최상위

| 필드 | 형식 | 설명 |
|---|---|---|
| `schema_version` | 정수 | 형식 버전. 필드 의미가 바뀌면 올린다. 읽는 쪽은 모르는 버전이면 무시하고 정상 동작해야 한다 |
| `generated` | 문자열 | 피드를 만든 시각(ISO 8601) |
| `source` | 문자열 | 이 저장소 주소 |
| `alerts` | 배열 | 알림 목록. 감지일 최신순 |

## alerts[]

| 필드 | 형식 | 설명 |
|---|---|---|
| `id` | 문자열 | 알림 id. 다시 실행해도 바뀌지 않는다. 고시 개정은 `문서id@고시번호`, 행정예고는 `notice:번호`, EU 법령은 `eu:CELEX` |
| `kind` | 문자열 | `revision`(고시 개정), `notice`(행정예고), `eu`(EU 법령) 중 하나 |
| `source_doc` | 문자열 | 추적 문서 id 또는 예고 번호·CELEX |
| `title`, `subtitle`, `url` | 문자열 | 표시용 제목, 비교 버전·기간 등 부가 정보, 원문 링크 |
| `detected` | 문자열 | 처음 감지한 날(YYYY-MM-DD) |
| `importance` | 문자열 | `high` / `medium` / `low` |
| `headline` | 문자열 | 한 문장 요약 |
| `actions` | 문자열 배열 | 실무자가 할 일 |
| `targets` | 배열 | 영향받는 코드·데이터. 없으면 빈 배열 |
| `note` | 문자열 | 요약 범위 등 참고 사항 |

## alerts[].targets[]

| 필드 | 형식 | 설명 |
|---|---|---|
| `target` | 문자열 | `config/impact_map.yaml`의 대상 id |
| `repo` | 문자열 | 저장소 이름. 읽는 쪽은 이 값으로 자기 몫을 고른다 |
| `path`, `symbol` | 문자열 | 바꿔야 할 파일과 변수·함수 |
| `importance` | 문자열 | 이 위치의 중요도 |
| `where`, `summary` | 문자열 | 바뀐 조항 위치와 내용 |
| `reason` | 문자열 | 이 대상과 관련된 이유 |

## 읽는 쪽 규칙

1. `targets[].repo`가 자기 저장소인 알림만 고른다.
2. 이미 반영한 알림 id는 자기 저장소의 확인 완료 파일(예: `data/reg_ack.json`)에 적어 두고 걸러 낸다.
3. 피드를 못 받아도(네트워크, 형식 버전 불일치) 본 기능은 그대로 동작해야 한다.
