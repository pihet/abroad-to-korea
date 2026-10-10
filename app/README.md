# app — 백엔드 (FastAPI)

`web/dist`(빌드된 화면)와 API를 한 서버(8000)로 제공한다. 실행·배포는 루트 README의 "실행"을 따른다.

```bash
docker compose up -d --build --no-deps api      # 코드 수정 후 (시작까지 약 40초)
docker compose restart api                      # 모델 자산 또는 DB 파생 인덱스를 다시 읽을 때
.venv/bin/uvicorn app.main:app --port 8001      # Docker 없이 확인할 때 (8000은 Docker가 쓴다)
```

| 파일 | 역할 |
|---|---|
| `main.py` | 앱 시작, 모든 API 경로, 사진·화면 파일 제공 |
| `recommender.py` | 추천 엔진: 사진 → 닮은 시군구 (CLIP, `src/model` 인덱스 함수를 읽기만 함) |
| `llm.py` | Ollama 자연어 요청 → 검증된 여행 조건·CLIP 텍스트 프롬프트 |
| `tags.py` | 사진 장면 태그 (CLIP 텍스트 유사도) |
| `context.py`, `regions.py` | 시군구 조건: 혼잡도(실측·예측), 날씨, 바다·산 등 필터 |
| `activities.py`, `courses.py`, `neighborhoods.py` | 지역 상세: 관광지·축제·음식점, 공식 여행코스, 읍·면·동 |
| `cost.py`, `travel_time.py`, `rain.py` | 예상 경비, 코스 이동 시간(카카오), 비 예보 |
| `search.py` | 이름 검색 (읍·면·동, 장소) |
| `schemas.py` | API 응답 모양 (`web/src/api.ts`와 같게 유지) |
| `auth.py`, `db.py`, `models.py`, `catalog.py`, `media.py`, `settings.py`, `query_cache.py`, `email_worker.py` | 로그인·DB 관광 콘텐츠 조회·업로드 사진 보관·캐시·메일 (인프라 담당) |
