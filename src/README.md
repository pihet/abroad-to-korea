# src — 데이터·모델 스크립트

서버가 아니라 사람이(또는 Airflow가) 직접 실행하는 스크립트. 저장소 루트에서 실행한다 (`python src/collect/tour_images.py`).
결과는 `data/raw`(원본), `data/interim`(가공)에 쌓이고 서버(`app/`)가 읽는다.

| 폴더 | 역할 | 주요 파일 |
|---|---|---|
| `collect/` | 공공데이터 수집. TourAPI는 `.env`의 키 여러 개를 하루 990건씩 돌려 쓴다 | `tour_attractions.py`(목록), `tour_images.py`, `tour_food_intro.py`, `tour_courses.py`, `tour_course_stops.py`, `datalab_visitors.py`, `region_context.py`(날씨·축제), `population.py`, `naver_food_images.py`·`naver_food_pick.py`(음식점 사진 보강) |
| `model/` | CLIP 유사도 실험·평가. 서버가 `clip_proto.py` 등의 인덱스 함수를 읽으므로 함수 이름을 바꾸지 않는다 | `clip_proto.py`(기본), `model_compare.py`, `kr_extra.py`, `reverify_dev.py`, `holdout_pilot.py`, `build_eval_sheet.py`(사람 평가 시트) |
| `forecast/` | 시군구 방문자(혼잡도) 예측 | `p1_spec.py`(기준 재현), `p1_holiday.py`(연휴 보정), `p1_congestion.py` |
| `cost/` | 국민여행조사로 시군구별 1인 경비 표 만들기 (원자료 `references/COST/`) | `build_cost_table.py` |
| `ingest/`, `ops/`, `mlops/` | MinIO·PostgreSQL 게시, 만료 사진 정리, MLflow 기록 (인프라 담당) | |

실행 순서와 결과 수치는 `docs/HANDOFF.md`에 장별로 있다.
