# DB 이전과 개인 맞춤 추천 설계 (2026-10-08)

지금 서비스 데이터는 전부 파일(`data/`)에 있고, Codex가 만든 PostgreSQL(`app/models.py`, 마이그레이션 `20261008_01`)은 테이블 21개가 모두 비어 있다.
이 문서는 (1) 누가 무엇을 하는지, (2) 어떤 파일을 어느 테이블로 옮기는지, (3) 로그인 사용자 개인 맞춤 재정렬을 어떻게 만드는지 정한다.

## 1. 분담과 규칙

| 담당 | 범위 | 파일 |
|---|---|---|
| Codex | Docker·DB·로그인·Airflow·MinIO, 파일 → DB 이전 스크립트, 피드백·저장 API의 DB 저장 | `docker-compose.yml`, `Dockerfile*`, `app/db.py`·`auth.py`·`models.py`·`media.py`·`settings.py`·`query_cache.py`, `migrations/`, `airflow/`, `infra/`, `src/ingest/`, `src/ops/` |
| Claude | 화면, 추천·평가 모델, 개인 맞춤 재정렬 계산, 문서 | `web/src/` (Codex의 `AccountModal.tsx` 제외), `app/recommender.py`·`regions.py`·`activities.py`·`courses.py`·`rain.py`·`search.py`, `src/prototype/`, `docs/` |

- **서로의 파일은 읽기만 한다.** 둘 다 고쳐야 하는 파일(`app/main.py`, `app/schemas.py`, `web/src/api.ts`)은 먼저 고친 쪽이 커밋한 뒤 다른 쪽이 `git pull` 하고 고친다.
- Codex는 지금 커밋되지 않은 인프라 작업을 **먼저 커밋**한다. 그전까지 Claude는 위 공유 파일을 고치지 않는다.
- **파일 버전을 지우지 않는다.** DB 버전이 같은 결과를 내는지 확인(아래 4장)될 때까지 파일 경로를 그대로 두고, 설정값 하나로 둘 중 하나를 읽게 한다 (예: `DATA_BACKEND=files|db`).
- 8000번 포트: 지금 로컬 개발 서버(파일 기반)와 Docker `api` 컨테이너가 둘 다 8000을 쓴다. 팀 공유 터널은 로컬 서버로 간다. 시연용 주 서버를 정할 때까지 Docker `api`는 다른 포트(예: 8001)로 옮기는 것을 권한다.

## 2. 파일 → DB 대응표 (2026-10-08 개수)

시군구 키는 `시도코드_시군구명` (예: `51_양양군`, `28_옹진군`)이다. 2026-07 개편으로 광주·전남은 시도명이 `전남광주통합특별시`다. 이 키를 그대로 `regions.key`로 쓴다.

| 데이터 | 지금 위치 | 개수 | 옮길 곳 | 메모 |
|---|---|---|---|---|
| 시군구 | 코드에서 계산 (`clip_proto.load_regions`, `regions.Regions.static`) | 230 | `regions` | 중심 좌표는 `region_context.region_centers()` |
| 관광지 (ct 12) | `data/raw/tourapi/areaBasedList2_ct12_20261002/page_*.json` | 12,603 | `places` (content_type=`attraction`) | `lclsSystm1~3`·`cpyrhtDivCd`는 `attributes`에 |
| 레포츠 (ct 28) | `areaBasedList2_ct28_20261004/` | 3,751 | `places` (`leports`) | |
| 음식점 (ct 39) | `areaBasedList2_ct39_20261006/` | 13,402 | `places` (`restaurant`) | 대표메뉴는 아래 |
| 대표메뉴 | `detailIntro2_ct39/<id>.json` | 9,881 (수집 중) | `places.attributes.menu` (`firstmenu`) | `app/activities._menu` 참고 |
| 축제 (ct 15) | `searchFestival2_20251001_20261231.json` | 883 | `festivals` | `eventstartdate`·`eventenddate` |
| 장소 소개글 | `detailCommon2/<id>.json` (누를 때 받음) | 13 | `places.attributes.overview` | 처음 볼 때 받는 방식 유지 |
| 대표사진 | 목록의 `firstimage` | 관광지 11,353장(임베딩 기준) | `place_images` (`is_primary=true`) | 공공누리 1·3유형만 (`license_code`) |
| 추가 사진 | `detailImage2/<id>.json` | 12,603곳, 항목 83,241개(전 유형) | `place_images` (`is_primary=false`) | 1·3유형만. 서비스 검색에는 쓰지 않음(15-26·27) |
| 음식점 추가 사진 | `detailImage2_ct39/<id>.json` | 10 (누를 때 받음) | `place_images` | |
| 사진 임베딩 (대표) | `data/interim/clip/emb_kr.npz` (`vecs` 11,353×512, `names`) | 11,353 | `image_embeddings` (`model_version=openai/clip-vit-base-patch32`) | **L2 정규화된 float32.** 서비스 검색이 쓰는 풀 |
| 사진 임베딩 (추가) | `emb_kr_extra.npz` (53,832×512) | 53,832 | `image_embeddings` | 평가용. 옮겨도 검색에는 넣지 않음 |
| 해외 예시 사진 | `data/external/overseas_scenes_v1_20261002.csv` + 사진 | 383 (예시 213) | 새 테이블 필요 없음, 파일 유지 가능 | 커먼즈 저작자·라이선스 열 포함 |
| 여행코스 | `areaBasedList2_ct25_20261007/`, `detailInfo2_ct25/`, `detailIntro2_ct25/` | 1,068 | **새 테이블** `courses`, `course_stops` | 아래 3장 |
| 동네(읍·면·동) 경계 | `data/interim/app/neighborhoods.json` (원본 `data/raw/admdongkor/`) | 3,558 | **새 테이블** `dongs` | GeoJSON은 JSONB로 (PostGIS 없음) |
| 방문자 수 (일별) | `data/raw/datalab/locgoRegnVisitrDDList/` | 2018-01 ~ 2026-08 | `visitor_metrics` (`basis=actual`) | 방문자 코드 → 시군구 키 연결은 `app/context._visit_key_map` 로직을 그대로 써야 한다 (구가 있는 시는 합산) |
| 방문자 예측 | 서버 시작 때 계산 (`make_demo_page.monthly_forecast`) | 230 × 1달 | `visitor_metrics` (`basis=forecast`) | 월 단위 ridge, 2025 검증 WAPE 5.6% |
| 날씨 (일별) | `data/raw/openmeteo/` | 파일 1,990개 (230곳 × 2021~2025) | `climate_daily` | |
| 주민등록 인구 | `data/raw/mois_population/202609/` | 파일 286개 | **새 열** `regions.urban_share` 또는 `regions` JSONB | 도시/시골 판정(동 거주 50%) |
| 해안 거리 | `data/interim/app/region_coast_km.json` | 230 | **새 열** `regions.coast_km` | 바다 칩(3km) |
| 피드백 | `data/interim/app/feedback.jsonl` | 25 | `feedback` (`user_id=NULL`) | 익명. 그대로 옮긴다 |
| 저장한 곳·최근 본 지역 | 각자 브라우저 localStorage (`feed-saved`, `feed-recent-regions`) | — | 로그인 사용자만 `saved_regions` | 비로그인은 지금처럼 브라우저 |

## 3. 새로 필요한 테이블 (Codex 작업)

```text
courses      (id PK = TourAPI contentid, title, distance_text, taketime_text, theme, region_keys TEXT[], raw_object_id)
course_stops (course_id FK, order INT, place_id FK NULL, name, overview, PRIMARY KEY(course_id, order))
dongs        (code PK = 행정동 코드, region_key FK, name, geometry JSONB, label_lat, label_lon, area)
regions      + coast_km FLOAT, urban_share FLOAT
```

- 코스의 지역은 원문 시군구 코드가 1,068개 중 52개에만 있어서, **들르는 곳이 있는 시군구**로 정한다 (`app/courses.py`). 이 규칙을 이전 스크립트에도 그대로 쓴다.
- 동네 Top 5·동네별 활동지·음식점 목록은 `places` 좌표와 `dongs` 경계로 계산할 수 있으니 따로 저장하지 않아도 된다(지금은 `neighborhoods.json`에 미리 계산해 둠).

## 4. 이전 확인 방법 (파일 버전과 같은 결과인가)

이전 뒤 `DATA_BACKEND=db`로 띄운 서버가 파일 버전과 아래가 같아야 한다. 같지 않으면 파일 버전을 계속 쓴다.

- `/api/regions` 230곳의 `flags`·`photo.attraction_id`
- 데모 사진 5장의 `/api/recommend` 상위 30곳 순서 (임베딩·투표가 같으면 완전히 같아야 한다)
- `/api/regions/51_양양군/profile` 의 12개월 방문자·동네 Top 5
- `/api/festivals?start=2026-10-07` 목록, `/api/regions/51_고성군/courses` 목록
- 기존 테스트 (`pytest tests -q`, 현재 32개)

## 5. 로그인 사용자 개인 맞춤 재정렬

### 원칙

- **로그인 사용자에게만** 적용한다. 비로그인은 지금과 똑같은 결과를 받는다.
- 사진이 닮은 후보 30곳 **안에서만 순서를 바꾼다.** 새 후보를 끌어오지 않는다 (사진 유사도가 주 신호라는 원칙, 시각 가중치 0.5 이상 유지).
- 좋아요·별로예요가 **3개 이상**일 때부터 켠다. 그전에는 꺼 둔다.
- 사용자가 끌 수 있다 (`user_preferences.preferences.personalize = false`). 탈퇴하면 피드백도 함께 지운다 (FK `ON DELETE`, 지금은 `SET NULL`이라 바꾸거나 별도 삭제 필요 → Codex 확인).

### 계산 (강화학습 대신 단순하고 설명 가능한 방식)

1. **취향 벡터**: 그 사용자가 좋아요한 후보의 대표사진 임베딩 합에서 별로예요한 후보 임베딩의 0.5배를 뺀 뒤 정규화한다.
   `u = normalize( Σ like e_i − 0.5 · Σ dislike e_j )`
   (`feedback.attraction_id` → `places` → `place_images.is_primary` → `image_embeddings`)
2. **후보 점수**: 후보 30곳 각각의 대표 관광지 임베딩 `e_c`로
   - 사진 점수 `v_c` = 지금 Stage A의 시각 순위를 30곳 안 백분위로 (1위=1.0)
   - 취향 점수 `p_c` = `cos(u, e_c)`의 30곳 안 백분위
   - 최종 `s_c = 0.8 · v_c + 0.2 · p_c` (취향 가중치 0.2로 시작, 0.3을 넘기지 않는다)
3. **설명**: 순위가 오른 후보에는 "내 취향 반영 ↑" 표시와 가장 비슷한 좋아요 사진 이름을 보여 준다 (예: "좋아요한 '을왕리해변'과 비슷").

### 저장·계산 위치

- 피드백: `feedback` (로그인 시 `user_id` 채움). 같은 후보에 다시 누르면 덮어쓴다 (이미 유니크 제약 있음).
- 취향 벡터: 요청마다 DB에서 계산해도 충분히 빠르다 (사용자당 피드백 수십 개). 필요하면 Redis `pref:{user_id}`에 두고 새 피드백이 오면 지운다.
- API: `/api/recommend` 응답 후보마다 `rerank.personal_component`(0~1 또는 null), `rerank.personal_reason`(문장 또는 null) 추가. 요청은 바뀌지 않는다 (로그인 쿠키로 판단).

### 평가 (작은 데이터라 "증명"이 아니라 "확인")

- **오프라인 확인**: 조원 각자의 피드백에서 마지막 좋아요 1개를 숨기고, 나머지로 만든 취향 벡터가 숨긴 후보의 순위를 올리는지(30곳 안) 본다. 사람 수가 적어 결과는 범위와 함께 적는다.
- **시연**: 새 계정으로 바다 사진에 좋아요 3번 → 같은 해외 사진 검색에서 바다 지역이 위로 오는 것을 보여 준다.
- 정확도 향상을 숫자로 주장하지 않는다. 기획서에는 "구조와 동작 확인, 효과 검증은 운영 데이터로"라고 적는다.

### 비로그인 피드백

- 지금처럼 익명으로 `feedback`(`user_id=NULL`)에 쌓는다. 개인 맞춤에는 쓰지 않는다.
- 나중에 조원 사람 평가 판정과 함께 **전체 사용자용 재정렬 모델**(로지스틱 회귀 등) 학습 데이터로 쓸 수 있다.

## 6. 작업 순서

1. Codex: 지금 인프라 작업 커밋 → Docker `api` 포트 정리
2. Codex: 3장 새 테이블 마이그레이션, 2장 이전 스크립트(시군구 → 장소 → 사진 → 임베딩 → 방문자·날씨 → 축제·코스·동네 → 피드백)
3. Codex: 4장 확인을 통과하면 `DATA_BACKEND=db` 기본값으로
4. Codex: 피드백 API에 `user_id` 저장, 로그인 사용자의 `saved_regions` 저장
5. Claude: 5장 재정렬 계산(`app/recommender.py`)과 화면 표시("내 취향 반영"), 오프라인 확인 스크립트
6. 둘 다: 시연 시나리오로 끝까지 확인

## 7. 정해야 할 것

- 탈퇴 시 피드백을 지울지 익명으로 남길지 (지금 FK는 `SET NULL` = 익명으로 남김)
- 시연은 Docker 스택으로 할지, 지금처럼 로컬 서버 + 터널로 할지
- 추가 사진 임베딩(53,832장)을 DB에 옮길지 (검색에는 안 쓰므로 생략 가능)
