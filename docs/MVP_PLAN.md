# MVP 계획: 사진으로 찾는 닮은꼴 국내 여행지 + 덜 붐비는 달

> 목표: 해외 여행지 사진을 올리면 분위기가 비슷한 국내 시군구·관광지를 찾고, 고른 달의 혼잡도와 12개월 흐름까지 한 화면에서 비교한다.
> 범위: P0 MVP. 기존 평가 코드(`src/prototype`, `src/forecast`)와 결과(`data/interim/clip/eval_*.json`)는 읽기만 하고 바꾸지 않는다.

## 1. 결정 사항 (2026-10-04)

| 항목 | 결정 |
|---|---|
| 백엔드 | FastAPI (Python). 기존 임베딩·모델 코드를 그대로 불러 쓴다 |
| 프론트엔드 | React + TypeScript (Vite). API 응답을 타입으로 고정해 UI가 모델 코드에 의존하지 않게 한다 |
| 시각 모델 | frozen CLIP ViT-B/32 유지 (11-9: 큰 모델이 더 낫지 않음) |
| 우선순위 | 사진과 최대한 비슷하게 / 덜 붐비는 곳 / 출발지에서 가까운 곳 / 고른 달에 가기 좋은 곳 |
| 제외 (후순위) | 가족 여행 적합도 (판단 근거 데이터 없음), 텍스트 조건("야경 제외" 등), 로그인·장기 개인화·일정 생성·예약·무드보드·실시간 카메라 |
| 날씨 | 230개 시군구 12개월 모두 수집 (Open-Meteo 2021~2025) |

## 2. 사용자 흐름과 화면

```
① 사진 고르기 → ② 영역 고르기 → ③ 장면 확인 → ④ 조건 → ⑤ 결과 → ⑥ 저장·비교·피드백
```

| 단계 | 화면 | 동작 |
|---|---|---|
| ① 사진 | 첫 화면. 서비스 한 줄 설명 + 큰 업로드 영역 + 데모 사진 격자 | 파일 업로드, 휴대폰 촬영(`capture`), 데모 사진(카탈로그 해외 사진, Commons 저작자 표시) |
| ② 영역 | 사진 위 드래그 크롭 상자 | "이 영역으로" 또는 "사진 전체 사용". 크롭 좌표는 원본 픽셀 기준으로 서버에 보낸다 (사용자 사진이므로 자르기 가능) |
| ③ 장면 | 태그 칩 (CLIP 제로샷, 상위 6개) | 칩 제거·추가. 태그는 결과 설명(비슷한 점·다른 점)에 쓰인다. 검색 순위에는 반영하지 않는다 (텍스트 조건과 함께 P1) |
| ④ 조건 | 여행 월(1~12), 우선순위 4개, 출발지(선택: 서울·부산·대구·광주·대전) | 바꾸면 결과를 즉시 다시 정렬 (서버에 저장된 질의 벡터 재사용) |
| ⑤ 결과 | 원본 사진 고정 + 국내 후보 카드 5개, "다른 후보 보기"로 30위까지 | 카드: 아래 3장 표 참고 |
| ⑥ 후속 | 카드마다 저장·비교 담기·좋아요/싫어요·지도 보기·"이 사진으로 다시 찾기" | 저장은 브라우저(localStorage), 피드백은 서버 파일(`data/interim/app/feedback.jsonl`)에 기록. 비교는 담은 후보 2~3곳을 항목별 표로 |

반응형: 모바일은 한 열(원본 사진 → 카드 세로 나열), 데스크톱은 원본 사진을 왼쪽에 고정하고 카드를 오른쪽에 둔다.

## 3. 결과 카드 항목과 데이터 출처 (실제 / 미지원 구분)

| 항목 | 출처 | 상태 |
|---|---|---|
| 관광지명, 시군구, 주소, 위도·경도 | TourAPI `areaBasedList2` (2026-10-02 수집) | 실제 |
| 대표 사진, 공공누리 유형, 출처 | TourAPI `firstimage`, `cpyrhtDivCd` | 실제. 1·3유형만 사용, 비율 유지·크롭·필터 없음 (`object-fit: contain`) |
| 시각 유사도 | CLIP 코사인 (원본 질의 ↔ 그 시군구에서 가장 닮은 관광지 사진) | 실제. 단독 점수가 아니라 "시각 순위"와 함께 표시 |
| 비슷한 점 / 다른 점 | 같은 태그 목록을 원본과 후보 사진에 CLIP으로 매겨 비교 | 실제 계산, 평가 전 기능 → "자동 비교(참고용)" 표시 |
| 고른 달 혼잡도 | 2026년 10월: 월 단위 예측 모델(HANDOFF 10-1, 2개월 전 시점). 그 밖의 달: 최근 12개월 실측(2025-09~2026-08)의 같은 달 | 실제. 값마다 "예측" 또는 "실측 YYYY-MM" 표시 |
| 12개월 혼잡도 그래프 | 최근 12개월 외지인 방문자 실측, 12개월 평균 = 100 | 실제 |
| 고른 달 날씨 | Open-Meteo 2021~2025년 그 달 평균기온·비 온 날 | 실제 |
| 거리 | 출발지 ↔ 시군구 중심(관광지 좌표 중앙값) 직선거리 | 실제 (도로 거리 아님) |
| 지도 | 카카오맵·네이버지도 좌표 링크 | 실제 |
| 데이터 기준일 | 각 원천의 수집일·기간을 응답에 포함 | 실제 |

예시 데이터는 쓰지 않는다. 데이터가 없으면 그 칸에 "자료 없음"을 표시한다.

## 4. 추천 구조

**Stage A: 시각 후보 (모델)**
1. 질의 사진(크롭 반영) → CLIP ViT-B/32 이미지 임베딩
2. 국내 관광지 대표사진 11,353장과 코사인 유사도 → 관광지 단위 통합 (관광지별 최고 1장)
3. 상위 100개 관광지의 유사도를 시군구별로 합산 (vote100) → 시군구 상위 30곳
   - 대표사진 풀에서는 기존 vote100과 결과가 같다 (HANDOFF 11-8에서 확인)
4. 시군구마다 "가장 닮은 관광지" 1곳과 시각 유사도를 함께 저장

**Stage B: 조건 재정렬 (규칙)**
- 30곳 안에서만 다시 정렬한다. 30위 밖은 올라오지 않는다
- `visual`: 시각 순위 그대로
- 그 밖: `0.5 × 시각 순위 점수 + 0.5 × 조건 백분위` (후보 30곳 안 기준, 시각 가중치는 0.5 아래로 내리지 않는다)
  - `crowd`: 고른 달 혼잡도 낮을수록
  - `near`: 출발지에서 가까울수록
  - `season`: 고른 달 쾌적도 높을수록 (기온 15~24°C 밖 감점, 비 온 날 감점)
- 응답에 시각 순위와 최종 순위, 조건별 값을 따로 담아 "왜 이 순서인가"를 설명한다
- 근거가 불명확한 단일 종합점수는 화면에 표시하지 않는다

## 5. API 계약

모든 응답에 `is_example: false`와 `data_sources`(원천·수집일·기간)를 포함한다.

### `GET /api/demo-photos`
데모용 해외 사진 목록: `[{photo_id, place_name, scene_label, image_url, artist, license, license_url, source_page}]`

### `POST /api/analyze` (multipart)
- 입력: `image`(파일) 또는 `demo_photo_id`, 선택 `crop`(`{"x","y","w","h"}` 원본 픽셀)
- 처리: 크롭 → 임베딩 → 장면 태그. 질의 벡터를 서버 메모리에 저장(최근 200개)
- 출력: `{query_id, scene_tags: [{tag, score}], image: {width, height, cropped}}`

### `POST /api/recommend` (JSON)
- 입력: `{query_id, travel_month: 1~12, priority: "visual"|"crowd"|"near"|"season", origin?: "서울"|..., kept_tags?: [..], limit?: 5, offset?: 0}`
- 출력:
```json
{
  "is_example": false,
  "query": {"query_id": "", "scene_tags": [], "month": 10, "priority": "visual", "origin": null},
  "model": {"visual": "CLIP ViT-B/32 (frozen), 관광지 최고 1장 → 시군구 vote100", "rerank": "Stage B 규칙 (시각 ≥ 0.5)"},
  "total_candidates": 30,
  "candidates": [{
    "rank": 1, "visual_rank": 1,
    "sigungu": {"key": "51_평창군", "name": "평창군", "sido": "강원특별자치도"},
    "attraction": {"id": "", "name": "", "address": "", "latitude": 0, "longitude": 0,
                   "image_url": "", "license": "공공누리 제1유형", "source": "한국관광공사 TourAPI"},
    "visual": {"similarity": 0.0, "vote": 0.0},
    "similar_tags": [], "different_tags": [],
    "congestion": {"month": 10, "index": 0, "visitors": 0, "basis": "forecast|actual", "basis_month": "2026-10",
                   "monthly": [{"month": "2025-09", "index": 0, "visitors": 0}]},
    "climate": {"month": 10, "temp_c": 0, "rain_days": 0, "comfort": 0},
    "distance_km": null,
    "map_links": {"kakao": "", "naver": ""},
    "rerank": {"visual_component": 1.0, "condition_component": null, "condition_value": null}
  }],
  "data_sources": [{"name": "", "as_of": "", "period": ""}]
}
```

### `POST /api/feedback` (JSON)
`{query_id, sigungu_key, attraction_id, value: 1|-1}` → `data/interim/app/feedback.jsonl`에 한 줄 추가

## 6. 파일 구성

| 경로 | 역할 |
|---|---|
| `app/main.py` | FastAPI 앱, 라우트, 정적 파일 (`web/dist`, 사진) |
| `app/schemas.py` | 요청·응답 pydantic 모델 (위 계약) |
| `app/recommender.py` | Stage A·B. `src/prototype`의 인덱스·투표 함수를 읽기 전용으로 사용 |
| `app/context.py` | 혼잡도(월별 실측·10월 예측), 날씨, 거리, 주소, 데이터 기준일 |
| `app/tags.py` | 장면 태그 목록과 CLIP 제로샷 |
| `web/` | React + TypeScript (Vite). `src/api.ts`에 응답 타입 |
| `tests/` | API 계약·실데이터 표시·라이선스 필드 테스트 |

## 7. 테스트와 완료 확인
- API: 데모 사진으로 analyze → recommend 흐름, 필드 존재·형식, `is_example` false, 공공누리 1·3유형만, 월 바꾸면 순서·혼잡도 기준월 변경
- 재정렬: `visual` 결과가 Stage A 순서와 같다. 다른 우선순위도 30위 밖 후보가 없다
- 기존 결과 보존: `data/interim/clip/eval_*.json` 해시가 작업 전후 같다
- 화면: 데스크톱·모바일 폭 캡처 각 1장 이상 (Playwright)

## 8. 후순위 (P1 이후)
가족 여행 적합도, 텍스트 조건(태그 검색 반영 포함), 지도 임베드, 당일 코스 생성, 로그인·장기 개인화, 무드보드, 실시간 카메라, 국내 사진 확대 반영(11-8 수집 완료 후)


## 추가된 API (2026-10-04)

- `POST /api/recommend` 에 `filters: ("sea"|"mountain"|"calm"|"mild")[]`, `sido?: string` 추가. 응답 `query.allowed_regions` = 조건을 통과한 시군구 수 (필터 없으면 null)
- `GET /api/regions?month=&origin=` — 시군구 230곳의 조건 값(`coast_km`, `mountain_n`, `visitors`, `congestion_index`, `temp_c`, `rain_days`), `flags`, 대표 사진, 출발지 거리. `filters[]`에 이름과 기준 문구
- `GET /api/activities?sigungu_key=&month=&attraction_id=` — 지역 활동 목록과 묶음별 개수, 기준 관광지(★)
- `GET /images/tour/{id}` — 활동 목록의 공공누리 1·3유형 썸네일 (목록에 있는 id만)

- 2026-10-06: 화면에서 여행 월 선택 제거. `travel_month`(recommend), `month`(regions·rankings·profile·activities)는 선택 값으로 남김. 없으면 월평균·연간 기준, `priority: "season"`과 `filters: ["mild"]`는 400
- `GET /api/regions/{key}/profile` — 지역 상세(12개월 기온·비·혼잡도, 읍·면·동 경계와 동네 Top 5, `focus` 지도 범위)
- `GET /api/rankings` — 둘러볼 만한 곳 목록(목록마다 조건 하나 + 정렬 기준 하나)
