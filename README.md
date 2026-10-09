# abroad-to-korea · 닮은꼴 국내 여행지

해외 여행지 사진을 올리면 분위기가 닮은 국내 시군구와 관광지를 찾아 주고, 고른 지역의 혼잡도·비 예보·동네별 할 거리와 먹거리를 보여 주는 웹서비스다.

교육 과정 팀 프로젝트(2026-10-01 ~ 2026-10-16)의 결과물이다. 진행 기록과 평가 수치는 [`docs/HANDOFF.md`](docs/HANDOFF.md), 인프라 운영 방법은 [`docs/INFRASTRUCTURE.md`](docs/INFRASTRUCTURE.md)에 있다.

## 지금 되는 것 (2026-10-08 기준)

메인 화면은 인스타그램형이다: 아래 탭 **홈**(분류 스토리 · 순위 줄 · 시군구 피드) · **탐색**(230곳 사진 격자) · **사진으로 찾기** · **저장**. 지역 바로가기는 `#region=51_양양군`.

| 화면 | 기능 |
|---|---|
| 시작 | 예시 한 쌍(교토 후시미 ↔ 종로구 창경궁 홍화문)으로 서비스 설명, 사진 올리기(아이폰 HEIC 포함)·해외 예시 사진, 사진 없이 둘러보기 |
| 조건 | 바다 가까운 곳 · 산·숲이 많은 곳 · 도시 / 시골·소도시 · 시도. 칩마다 기준과 남는 시군구 수 표시 |
| 순위 목록 | 산·숲이 많은 곳, 할 거리가 많은 시골·소도시, 앞으로 축제가 많이 열리는 곳 (목록마다 거르는 조건 하나 + 정렬 기준 하나, 종합점수 없음) |
| 사진 검색 | 관심 영역 자르기 → 장면 태그 → 우선순위(사진과 최대한 비슷하게 / 출발지에서 가까운 곳) → 닮은 시군구 최대 30곳 |
| 결과 | 원본·후보 사진 나란히, 전국 지도 번호 핀, 비슷한 점·다른 점, 2~3곳 비교표, 저장(브라우저), 좋아요·별로예요, 이 사진으로 다시 찾기 |
| 지역 상세 | **혼잡도 한 줄 요약**(이번 달 예측 + 가장 한산했던 달 실측), **여행 날짜에 비가 올까**(16일 안은 일기예보, 그 밖은 과거 5년 같은 날짜 기록) |
| 동네와 먹거리 | 읍·면·동 경계 지도에 활동지가 많은 동네 Top 5. 동네를 누르면 확대되며 활동지가 점으로 나오고(누르면 사진·설명), 아래에 음식점·대표메뉴, 사진을 누르면 추가 사진 |
| 할 만한 것 | 물·바다, 산·숲, 레저, 캠핑, 체험, 먹거리, 축제를 지도와 목록으로 |
| 코스 | 한국관광공사 공식 여행코스(시군구 212곳): 들르는 순서대로 지도 번호 핀·점선, 사진·설명·소요시간 |

즉시 활성화되는 이메일 회원가입·일반 로그인과 Google·Kakao OAuth, 서버 저장 지역, 사용자 사진 보관 동의·삭제 API가 구현되어 있다. 비밀번호 재설정 메일은 Resend로 발송하며, OAuth 운영 키는 별도로 관리한다.

빠진 것: 개인화 추천, 예약·결제, 여행 총비용, 이동 시간 기반 일정.

## 현재 아키텍처

```mermaid
flowchart TB
  U["브라우저<br/>React + TypeScript + Leaflet"]
  DBA["DBeaver<br/>127.0.0.1:5434"]

  subgraph DC["Docker Compose"]
    API["FastAPI :8000<br/>추천 · 지역 상세 · 회원 · 사진 API"]
    MIG["Alembic migration<br/>기동 시 스키마 적용"]
    PG[("PostgreSQL + pgvector<br/>app · Airflow · MLflow DB<br/>container :5432")]
    REDIS[("Redis :6379<br/>세션 · OAuth state · rate limit · 검색 캐시")]
    MINIO[("MinIO<br/>S3 API :9000 · Console :9001<br/>사용자 사진 · Bronze 원본 · 관광 사진")]
    AFUI["Airflow API server :8080"]
    AFDP["Airflow DAG processor<br/>DAG 파싱 · 등록"]
    AFS["Airflow scheduler<br/>LocalExecutor"]
    MLF["MLflow :5000<br/>실험 · 지표 · artifact 추적"]
  end

  STAGE[("호스트 data/<br/>수집 staging · 모델 · 경계 · 임베딩")]
  EXT["외부 서비스<br/>TourAPI · DataLab · Open-Meteo<br/>OpenStreetMap · Google · Kakao"]

  U <-- "HTTPS / JSON / 이미지" --> API
  U -. "지도 타일" .-> EXT
  API --> PG
  API --> REDIS
  API --> MINIO
  API --> STAGE
  API --> EXT
  DBA -- "host 5434 → container 5432" --> PG
  MIG -- "app 스키마" --> PG
  AFUI --> PG
  AFDP -- "DAG 등록" --> PG
  AFS --> PG
  AFS -- "DAG 실행" --> STAGE
  AFS -- "공공데이터 수집" --> EXT
  AFS -- "정규화·upsert" --> PG
  AFS -- "원본·사진 보관" --> MINIO
  AFS -- "캐시 무효화" --> REDIS
  MLF -- "run · parameter · metric" --> PG
  MLF -- "모델 평가 artifact" --> MINIO
  STAGE -. "학습·평가 기록" .-> MLF
```

PostgreSQL이 회원·저장 지역·수집 데이터의 원본이며 Redis는 재생성 가능한 캐시다. MinIO는 사용자 업로드와 원본 응답·사진 파일을 보관한다. 사용자 사진은 로그인 사용자가 보관에 동의한 경우에만 저장하고, 동의하지 않으면 분석 후 저장하지 않는다.

Airflow는 관광 사진·음식·축제·카탈로그를 매일 수집해 검증 후 PostgreSQL에 upsert하고 MinIO에 원본을 보관한다. 사용자 사진 정리는 매시간, 방문자·인구 데이터는 매월 실행한다. 현재 cron은 UTC 기준이며 정확한 시각은 [`docs/INFRASTRUCTURE.md`](docs/INFRASTRUCTURE.md)에 정리되어 있다.

| 접속 대상 | 호스트 주소 | 용도 |
|---|---|---|
| 웹/API | `http://localhost:8000` | 서비스와 API 문서(`/docs`) |
| Airflow | `http://localhost:8080` | DAG 확인·운영 |
| MLflow | `http://localhost:5000` | CLIP·혼잡도 실험 비교 |
| PostgreSQL | `127.0.0.1:5434` | DBeaver, 컨테이너 내부 포트는 `5432` |
| Redis | `localhost:6379` | 개발용 캐시 확인 |
| MinIO | `http://localhost:9000`, `http://localhost:9001` | S3 API, 관리 콘솔 |

## 데이터

| 데이터 | 출처 | 용도 |
|---|---|---|
| 국문 관광정보 (KorService2) | 한국관광공사 / 공공데이터포털 | 관광지 12,603곳·레포츠·축제·음식점 13,402곳, 사진(공공누리 1·3유형만), 대표메뉴 |
| 빅데이터 지역별 방문자수 (DataLabService) | 한국관광공사 / 공공데이터포털 | 시군구별 외지인 방문자 수 2018-01 ~ 2026-08, 혼잡도 예측 학습 |
| 특일 정보 | 한국천문연구원 / 공공데이터포털 | 공휴일 (연휴 예측) |
| 행정동별 주민등록 인구 | 행정안전부 / 공공데이터포털 | 도시 / 시골·소도시 구분 |
| 행정동 경계 (admdongkor ver20260701) | vuski/admdongkor, CC BY 4.0 (원자료 통계청 SGIS) | 동네 지도 |
| 해안선 | Natural Earth (퍼블릭 도메인) | 바다 가까운 곳 |
| 날씨 | Open-Meteo, CC BY 4.0 | 과거 일별 기록(2021~2025), 16일 일기예보 |
| 해외 예시 사진 | Wikimedia Commons (사진별 라이선스) | 데모 사진 |

데이터 파일은 저장소에 넣지 않는다. 출처와 다시 받는 방법은 [`data/README.md`](data/README.md)에 있다.

관광지 추가 사진과 음식점 대표메뉴는 하루 한도(990건)로 나눠 받았고 2026-10-09에 모두 받았다.

## 폴더

역할별로 나눴다. 폴더마다 README가 있다.

```
app/           백엔드 (FastAPI): API, 추천, 조건, 지역 상세, 예상 경비, 이동 시간
web/           프론트 (React + Vite): 탐색 피드, 사진으로 찾기, 지역 상세
src/           데이터·모델 스크립트 (서버가 아니라 직접 실행)
  collect/     공공데이터 수집 (TourAPI, 데이터랩, 네이버 이미지 등)
  model/       CLIP 유사도 실험·평가 (서버가 인덱스 함수를 읽음)
  forecast/    방문자(혼잡도) 예측
  cost/        예상 경비 표 만들기
  ingest/      원본 보관, 검증, PostgreSQL 게시, 사진 캐시
  ops/         만료된 사용자 사진 정리
  mlops/       MLflow 실험 기록
infra/         배포·운영
  docker/      보조 서비스 Dockerfile과 의존성 (Airflow, MinIO, MLflow)
  airflow/     배치 스케줄 (DAG)
  migrations/  Alembic DB 스키마 변경 이력 (alembic.ini 도 여기)
  postgres/    최초 DB·계정 생성
  mlflow/      MLflow 서버 시작
tests/         pytest
tools/         진행 기록 PPT 생성 스크립트
docs/          HANDOFF(진행 기록) · MVP_PLAN(화면·API 계약) · ARCHITECTURE(구성도) · INFRASTRUCTURE(운영)
data/          데이터 (파일은 Git 제외, 출처는 data/README.md)
references/    로컬 참고 자료 (경비 원자료 COST, 카카오맵 검증 Map). Git 제외
Dockerfile, docker-compose.yml, requirements*.txt   API 이미지와 전체 실행 (루트에 둔다)
```

## 실행

### Docker Compose로 전체 실행

```bash
# 최초 실행일 때만 .env.example을 복사하고 비밀번호·API 키를 채운다.
cp .env.example .env

docker compose config --quiet
docker compose up --build -d
docker compose ps
```

기존 `.env`에 API 키가 있다면 복사 명령으로 덮어쓰지 않는다. 현재 로컬 PostgreSQL과의 충돌을 피하기 위해 서비스 DB는 호스트의 `5434` 포트를 사용한다. DBeaver 기본 접속값은 `127.0.0.1:5434`, DB `abroad_to_korea`, 사용자 `app`이며 비밀번호는 `.env`의 `APP_DB_PASSWORD`다.

### 로컬에서 직접 실행

```bash
python -m venv .venv && source .venv/bin/activate
pip install pandas numpy scikit-learn python-dotenv holidays lightgbm
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install transformers pillow
pip install fastapi==0.118.0 "uvicorn==0.37.0" python-multipart==0.0.20 pillow-heif==1.8.0 shapely==2.1.2
pip install -r infra/docker/requirements-mlflow.txt

# .env의 TOUR_API_KEY에 포털 표시값을 입력한다. 기존 .env를 덮어쓰지 않는다.
# 키를 더 가지고 있으면 TOUR_API_KEY_2, TOUR_API_KEY_3 … 으로 추가: 매일 수집이 한 키의 하루 한도가 차면 다음 키로 넘어간다
```

LightGBM은 Linux/WSL에서 `sudo apt install -y libgomp1`이 먼저 필요하다.
검증한 버전: Python 3.12, pandas 2.2.3, numpy 2.1.3, scikit-learn 1.5.2, holidays 0.105, lightgbm 4.7.0, torch 2.14.1(CPU), transformers 5.18.0.

MLflow UI는 `http://localhost:5000`에서 확인한다. `model_compare.py evaluate`, `p1_spec.py`, `p1_holiday.py` 실행 결과는 로컬 JSON을 먼저 저장한 뒤 MLflow에도 기록된다. MLflow가 꺼져 있으면 실험 자체는 완료되고 콘솔에 기록 실패 경고가 나온다.

### 데이터 받기

```bash
python src/collect/tour_attractions.py                     # 관광지 목록
python src/collect/tour_attractions.py 28                  # 레포츠
python src/collect/tour_attractions.py 39                  # 음식점
python src/collect/datalab_visitors.py                     # 지역별 방문자 수
python src/forecast/p1_spec.py kasi                        # 방문자 예측 기준 재현
python src/collect/region_context.py climate 10            # 날씨 (다른 달: climate 1 2 3 ...)
python src/collect/region_context.py festivals 20251001 20261231   # 축제
python src/collect/population.py                           # 행정동 인구 (별도 활용신청)
# 동네 경계: data/raw/admdongkor/ 에 vuski/admdongkor ver20260701 HangJeongDong_ver20260701.geojson

# 매일 자정 이후 (하루 한도 990건씩 이어 받기)
python src/collect/tour_images.py 930                      # 관광지 추가 사진
python src/collect/tour_food_intro.py                      # 음식점 대표메뉴
python src/collect/tour_attractions.py 25 && python src/collect/tour_courses.py   # 여행코스 (구성·소요시간, 이어 받기)
```

### 서버 띄우기

```bash
cd web && npm install && npm run build && cd ..            # 화면 빌드 → web/dist
uvicorn app.main:app --port 8000                           # 첫 실행 때 CLIP 로딩 20~40초
# → http://localhost:8000  (API 문서: http://localhost:8000/docs)
```

화면을 고치면서 볼 때는 서버를 띄운 채로 `cd web && npm run dev` (http://localhost:5173, API는 8000으로 넘어간다).
수집한 데이터는 서버를 다시 띄워야 반영된다.

테스트: `pip install pytest httpx && python -m pytest tests -q`
기존 평가 결과·임베딩·코드가 바뀌지 않았는지(`data/interim/app/baseline_hashes.txt`)도 함께 검사한다.

## 현재 수치 (자세한 조건은 HANDOFF)

- 사진 유사도 (CLIP, 개발셋 해외지 23곳): 정답 시군구 Hit@5 57%, Hit@10 74% (무작위 약 4%·8%)
  - 처음 보는 해외지 15곳 파일럿: Hit@10 40%. 도시 장면은 강하고 특정 지점형 정답은 약하다
  - 사람 평가(평가자 1명, 30곳 × 후보 5곳): 그럴듯함 69%, 엉뚱함 16%. 조원 2~3명 평가 예정
- 방문자 예측 (검증 2025)
  - 월 단위 (서비스에 쓰는 모델): WAPE 5.6% (전년 같은 달 기준선 7.7%)
  - 일 단위: 전체 WAPE 7.3%, 연휴 관련일 13.2% (기준선 9.9% / 28.2%)

## 남은 일

- 조원 사람 평가와 새 테스트셋, 사진 수집이 끝난 뒤 재평가
- 관광지별 집중률(한국관광공사 예측 API)을 동네 지도 점에 표시 (활용신청 반영 대기)
- 서버를 다시 띄워도 분석 결과 유지(#3), 재시작 없이 새 데이터 반영(#2)
- 운영 인프라 실제 기동 검증, 메일 발송 업체 연결, 발표자료
