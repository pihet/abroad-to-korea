# 시스템 아키텍처 (지금 돌아가는 구조, 2026-10-07)

해외 여행지 사진 → 분위기가 닮은 국내 시군구·관광지 → 지역 상세(혼잡도·비 예보·동네·먹거리).
화면(React)과 서버(FastAPI)는 HTTP API로만 연결된다. 화면은 `web/src/api.ts`의 타입만 알고 모델 코드는 모른다.
운영 구조(Docker·Airflow·Redis·Postgres)는 아직 설계 단계라 여기 넣지 않았다.

## 1. 전체 구성

```mermaid
flowchart TB
  B["<b>① 브라우저</b> · web/ (React + TypeScript + Vite)<br/>시작: 조건 칩 · 순위 목록 · 사진 없이 둘러보기<br/>사진 검색: 자르기 → 장면 태그 → 결과 카드 · 전국 지도 · 비교<br/>지역 상세: 혼잡도 요약 · 비 예보 · 동네 지도 · 음식점<br/>저장한 곳: localStorage"]
  A["<b>② main.py</b> · REST API (FastAPI, 한 프로세스)<br/>/api/analyze · /api/recommend · /api/regions/…/profile<br/>/api/regions/…/rain · /api/regions/…/dongs/… · /api/places/…/photos"]
  M["<b>③ 서버 안 모듈</b> (시작할 때 모두 메모리에 올림)<br/>recommender.py: CLIP ViT-B/32(학습 없음) · 국내 사진 인덱스 · 질의 캐시 200건<br/>context.py: 방문자 12개월 실측 · 월 단위 예측(ridge)<br/>regions.py: 조건 필터·순위 · activities.py: 관광지·레포츠·축제·음식점<br/>neighborhoods.py: 읍·면·동 경계·동네 Top 5 · rain.py: 비 예보"]
  D[("<b>④ 로컬 데이터</b> · data/ (Git 제외)<br/>TourAPI 목록·추가 사진·대표메뉴 · 방문자 수 2018-01 ~ 2026-08<br/>과거 날씨 2021~2025 일별 · 인구·경계·해안선<br/>임베딩·썸네일·캐시 · feedback.jsonl")]
  X["<b>⑤ 서비스 중 호출하는 외부</b><br/>Open-Meteo 일기예보(16일 안)<br/>TourAPI 원본·추가 사진(처음 한 번, 캐시)<br/>OpenStreetMap 지도 타일"]

  B -- "요청" --> A
  A -- "응답: JSON · 사진" --> B
  A --> M
  M -- "읽기" --> D
  M -- "일기예보 · 사진" --> X
  B -. "지도 타일" .-> X
```

## 2. 미리 돌려 두는 배치

```mermaid
flowchart LR
  subgraph E["외부 공공데이터"]
    T["TourAPI<br/>KorService2"]
    V["관광 빅데이터<br/>방문자수"]
    W["Open-Meteo<br/>과거 날씨"]
    M["행정안전부 인구"]
    C["Wikimedia Commons"]
  end
  subgraph J["수집·학습 (src/)"]
    J1["collect/tour_attractions.py<br/>관광지·레포츠·음식점 목록"]
    J2["collect/tour_images.py<br/>추가 사진 (매일 930건)"]
    J3["collect/tour_food_intro.py<br/>대표메뉴 (매일 990건)"]
    J4["collect/datalab_visitors.py"]
    J5["forecast/p1_spec.py<br/>월 단위 예측 학습"]
    J6["collect/region_context.py<br/>날씨 · 축제"]
    J7["collect/population.py"]
    J8["prototype/<br/>CLIP 임베딩 · 평가"]
  end
  D[("data/")]
  T --> J1 & J2 & J3 & J6
  V --> J4 --> J5
  W --> J6
  M --> J7
  C --> J8
  J1 & J2 & J3 & J4 & J5 & J6 & J7 & J8 --> D
```

지금은 손으로 돌린다. 매일 자정 이후 `tour_images.py`와 `tour_food_intro.py`를 돌리고, 서버를 다시 띄워야 새 데이터가 반영된다(이슈 #2).

## 3. 요청 흐름

### 사진으로 찾기

```mermaid
sequenceDiagram
  autonumber
  actor U as 사용자
  participant W as React 화면
  participant A as FastAPI
  participant E as Engine (CLIP)

  U->>W: 사진 선택, 영역 자르기
  W->>A: POST /api/analyze (사진, 자를 영역)
  A->>E: 회전 보정 · 자르기 · 임베딩(512차원)
  E-->>A: query_id, 장면 태그
  A-->>W: 태그 표시
  U->>W: 우선순위 · 출발지 · 조건 칩
  W->>A: POST /api/recommend (query_id, 우선순위, 조건)
  A->>E: 조건 필터로 시군구를 거른 뒤 Stage A (관광지별 최고 1장 → 상위 100곳 시군구 합산 → 30곳)
  E->>E: Stage B: 30곳 안에서만 재정렬 (시각 가중치 0.5 이상)
  E-->>A: 후보 카드 (사진 · 유사도 순위 · 비슷한 점/다른 점 · 거리 · 지도 링크 · 라이선스)
  A-->>W: 결과 카드 + 전국 지도 핀
```

### 지역 상세

```mermaid
sequenceDiagram
  autonumber
  actor U as 사용자
  participant W as React 화면
  participant A as FastAPI
  participant O as Open-Meteo

  U->>W: "자세히 보기"
  W->>A: GET /api/regions/{key}/profile
  A-->>W: 12개월 방문자(실측 + 이번 달 예측) · 동네 경계 · Top 5
  W->>A: GET /api/regions/{key}/rain?start&end
  alt 오늘부터 16일 안
    A->>O: 일별 강수확률 · 강수량
    O-->>A: 예보
  else 그보다 먼 날짜
    A->>A: 2021~2025년 같은 날짜 기록
  end
  A-->>W: 비 예보 (근거 구분: 예보 / 과거 기록)
  U->>W: 동네 번호 누르기
  W->>A: GET /api/regions/{key}/dongs/{code}/activities · /food
  A-->>W: 활동지 점 · 음식점과 대표메뉴
  U->>W: 음식점 사진 누르기
  W->>A: GET /api/places/{id}/photos
  A-->>W: 추가 사진 (없으면 TourAPI에서 한 번 받아 저장)
```

## 4. 설계 원칙

| 원칙 | 구현 |
|---|---|
| 화면과 모델 분리 | 화면은 `web/src/api.ts` 타입만 안다. 모델 교체 시 `app/recommender.py`만 바꾼다 |
| 조건은 거르기, 사진은 순서 | 조건 필터는 후보 풀을 줄이고(기준을 화면에 표시), 그 안에서 사진 유사도로 30곳을 고른다 |
| 혼잡도는 검색이 아니라 지역 정보 | 검색 조건·우선순위에서 빼고 지역 상세에서만 보여 준다. 예측과 실측을 구분해 표시 |
| 단일 종합점수 없음 | 카드와 순위 목록에 기준 하나씩만 쓰고 그 기준을 적는다 |
| 근거 있는 값만 | 자료가 없으면 "자료 없음". 과거 날씨 기록을 예보처럼 쓰지 않는다 |
| 이미지 라이선스 | 공공누리 1·3유형만, 자르기·필터·글자 덮기 없이, 출처 표시 |
| 기존 연구 코드 보존 | `src/prototype`과 평가 결과는 읽기만. 테스트가 해시로 확인 |

## 5. 한계와 다음 단계

- 한 프로세스: 모델·인덱스·질의 캐시가 서버 메모리에 있어 재시작하면 분석 결과가 사라진다(#3). 캐시는 Redis, 인덱스는 벡터 DB(FAISS 파일 또는 pgvector)로 옮길 수 있다.
- 배치는 손으로 돌린다. Airflow 같은 스케줄러로 매일 수집 → 서버 반영을 묶는 것이 다음 단계다.
- OpenStreetMap 공식 타일은 시연용이다. 실제 서비스에서는 상용 타일이나 카카오맵으로 바꾼다.
- 피드백은 파일에 쌓이기만 한다. 평가 지표와 함께 보는 집계는 아직 없다.
