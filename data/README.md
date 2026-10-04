# data/

데이터 파일 **본체는 Git에 올리지 않는다.** 이 폴더는 구조와 설명만 공유한다.

| 폴더 | 용도 | 수정 가능 여부 |
|---|---|---|
| `raw/` | 내려받은 원본. 절대 수정하지 않는다. | 읽기 전용 |
| `external/` | 외부에서 추가로 가져온 참고 데이터 | 읽기 전용 |
| `interim/` | 전처리 중간 결과 | 재생성 가능 |
| `processed/` | 모델 학습에 바로 쓰는 최종 데이터 | 재생성 가능 |

## 규칙

1. `raw/`에 넣은 파일은 이름도 내용도 바꾸지 않는다. 가공은 반드시 사본으로 한다.
2. `interim/`, `processed/`는 코드로 다시 만들 수 있어야 한다. 사라져도 문제없어야 한다.
3. 데이터를 새로 추가하면 아래 표에 출처를 기록한다.
4. 실제 파일은 팀 공유 드라이브로 주고받는다. (링크: 주제 확정 후 조장이 공유)

## 데이터 출처 기록

| 파일명 | 출처 / URL | 라이선스 | 받은 날짜 | 크기 | 담당자 |
|---|---|---|---|---|---|
| `raw/tourapi/areaBasedList2_ct12_<날짜>/` | 한국관광공사 국문 관광정보 서비스_GW (KorService2) / https://www.data.go.kr/data/15101578/openapi.do | 공공누리 (사진은 항목별 `cpyrhtDivCd` 확인. 표시 없는 사진은 웹에 쓰지 않음) | 2026-10-02 | 8.5MB, 13페이지, 12,603건 | 조장 |
| `raw/tourapi/ldongCode2_list_20261002.json` | 같은 API의 `ldongCode2` (법정동 시군구 코드·이름 269개) | 공공누리 | 2026-10-02 | 1파일 | 조장 |
| `raw/datalab/locgoRegnVisitrDDList/<YYYYMM>.json.gz` | 한국관광공사 빅데이터 지역별 방문자수_GW (DataLabService `locgoRegnVisitrDDList`), `src/collect/datalab_visitors.py` | 공공누리 | 2026-10-02 | 104개월(2018-01~2026-08), gzip 25MB | 조장 |
| `raw/nager/KR_<연도>.json` | Nager.Date 공휴일 API / https://date.nager.at (P1 명세 재현용, Aside 원본과 같은 출처) | TODO: 데이터 라이선스 미확인 | 2026-10-02 | 10파일 (2017~2026) | 조장 |
| `raw/tourapi/detailImage2/<contentid>.json` | 같은 TourAPI의 `detailImage2` (관광지별 추가 이미지), `src/collect/tour_images.py`. 하루 990건씩 이어받기 | 공공누리 (이미지별 `cpyrhtDivCd`) | 2026-10-02~ | 1일차 990곳 / 전체 12,603곳 | 조장 |
| `interim/clip/kr_extra/`, `emb_kr_extra.npz` | 위 추가 이미지 중 공공누리 1·3유형, 관광지당 최대 5장, 긴 변 400px. `src/prototype/kr_extra.py`로 재생성 | 공공누리 1·3유형 | 2026-10-02 | 4,272장 (1일차) | 조장 |
| `raw/openmeteo/archive_<시도코드>_<시군구>.json` | Open-Meteo Historical Weather API, `src/collect/region_context.py climate` (시군구 중심 좌표) | CC BY 4.0 | 2026-10-04 | 230곳 (70곳 2016~2025 전체, 160곳 2021~2025년 10월만) | 조장 |
| `raw/tourapi/searchFestival2_20261001_20261031.json` | TourAPI `searchFestival2`, `region_context.py festivals` | 공공누리 | 2026-10-04 | 축제 257건 | 조장 |
| `interim/p1/results.json` | P1 혼잡도 예측 평가 결과. `src/forecast/p1_congestion.py`로 재생성 | — | 2026-10-02 | 재생성 가능 | 조장 |
| `interim/clip/` | CLIP 프로토타입 캐시 (국내 썸네일, Commons 해외 사진 원본·정리본(`overseas_curated/`), 임베딩). `src/prototype/clip_proto.py`로 재생성 | 국내: 공공누리 1·3유형 / 해외: 사진별 CC·PD (`overseas/attribution.json`) | 2026-10-02 | 재생성 가능 | 조장 |
| `interim/clip/scenes/`, `emb_scenes.npz`, `scene_recs.csv` | 장면 카탈로그 v1(`external/overseas_scenes_v1_20261002.csv`) `qa_status=ok` 383장의 Commons 썸네일과 장면별 추천. `src/prototype/scene_catalog.py`로 재생성 | 사진별 CC BY-SA·CC BY·CC0·PD (카탈로그 CSV의 license·artist 열) | 2026-10-02 | 383장 | 조장 |
| `external/overseas_candidates.csv` | 직접 작성. 좌표는 Open-Meteo Geocoding API (GeoNames 기반) / https://open-meteo.com/en/docs/geocoding-api | 좌표: CC BY 4.0 (GeoNames) | 2026-10-02 | 30행 | 조장 |
| `external/ground_truth_pairs.csv` | 직접 작성. 행마다 `source_url`에 원문 기사 링크와 인용문 기록 | 인용문은 출처 표기 후 짧게 인용 | 2026-10-02 | 30행 (평가용 19) | 조장 |
| `external/tour_osm_category_map.csv` | 직접 작성. TourAPI 신분류(`lclsSystmCode2`) ↔ OSM 태그 대응 | — | 2026-10-02 | 10행 | 조장 |
| `external/ground_truth_pairs_candidates_20261002.csv` | 직접 작성(Aside). 행마다 `source_url`·인용문. **팀 검토 후 `ground_truth_pairs.csv`에 병합 예정** | 인용문은 출처 표기 후 짧게 인용 | 2026-10-02 | 29행 (평가용 제안 22) | 조장 |
| `external/ground_truth_pairs_candidates_round2_20261002.csv` | 11-2 쏠림 평가 보강용 후속 조사(Aside). 공공기관·주요/지역 언론 원문 확인. 현재 카탈로그 장면 대응 여부까지 검토 | 인용문은 출처 표기 후 짧게 인용 | 2026-10-02 | 25행 (평가용 제안 14, 보류 11) | 조장 |
| `external/ground_truth_overseas_id_aliases_20261002.csv` | 기존 정답 해외 id를 107곳 카탈로그 id에 연결 (`brooklyn→nyc`, `montmartre→paris`, `sahara_merzouga→merzouga`) | — | 2026-10-02 | 3행 | 조장 |
| `external/ground_truth_dev_v1_20261002.csv` | 기존에 결과를 확인한 개발·가중치 선택용 정답. 별칭 id 정규화 포함 | 기존 원문별 짧은 인용 | 2026-10-02 | 41쌍 / 해외지 23곳 | 조장 |
| `external/ground_truth_holdout_new_v1_20261002.csv` | 새 해외지만 분리한 미평가 홀드아웃. **최종 수집 완료 전 CLIP 결과를 보지 않음** | 원문별 짧은 인용 | 2026-10-02 | 15쌍 / 해외지 15곳 | 조장 |
| `external/ground_truth_dev_label_additions_v1_20261002.csv` | 기존 개발 해외지의 새 국내 정답(뉴욕·그랜드캐니언·우유니·몰디브) | 원문별 짧은 인용 | 2026-10-02 | 4쌍 | 조장 |
| `external/ground_truth_holdout_pending_v1_20261002.csv` | 출처·비교 강도 문제로 홀드아웃에 아직 넣지 않은 후보 | 원문별 짧은 인용 | 2026-10-02 | 6쌍 | 조장 |
| `external/ground_truth_split_manifest_20261002.csv` | 해외지별 dev/holdout/보강/pending 분할과 정답 쌍 수 | — | 2026-10-02 | 48행 (고유 해외지 44곳) | 조장 |
| `external/overseas_scenes_holdout_additions_20261002.csv` | 홀드아웃 누락 장면 5개 × Commons 사진 2장. 라이선스·작가·원본 URL 포함, 모델 결과 확인 전 고정 | 사진별 CC BY-SA / CC BY / CC0 | 2026-10-02 | 10장 | 조장 |
| `interim/clip/scenes_holdout/`, `emb_scenes_holdout.npz` | 위 홀드아웃 보강 사진과 별도 CLIP 임베딩. `src/prototype/holdout_scene_embeddings.py`의 `download validate embed`로 재생성하며 추천·평가는 수행하지 않음 | 사진별 CC BY-SA / CC BY / CC0 | 2026-10-02 | 10장 / 5개 장면 / 512차원 | 조장 |
| `external/overseas_candidates_additions_20261002.csv` | 위 후보의 새 해외 지명 좌표. Open-Meteo Geocoding API | 좌표: CC BY 4.0 (GeoNames) | 2026-10-02 | 13행 | 조장 |
| `external/overseas_places_v1_20261002.csv` | 직접 작성(Aside). 해외 여행지 107곳. 좌표는 Open-Meteo Geocoding(국가 지정), 테를지만 영문 위키백과 좌표 | 좌표: CC BY 4.0 (GeoNames) | 2026-10-02 | 107행 | 조장 |
| `external/overseas_scenes_v1_20261002.csv` | Wikimedia Commons API. 장면별 사진 메타데이터(원본·썸네일 URL, 라이선스, 작가). 사진 파일 본체는 받지 않음. `qa_status=ok`만 사용 | 사진별 CC BY / CC BY-SA / CC0 / PD (행마다 기록) | 2026-10-02 | 451행 (ok 383) | 조장 |
| `external/kr_holidays_2018_2027.csv` | 한국천문연구원 특일정보 API `getRestDeInfo` / https://www.data.go.kr/data/15012690/openapi.do | 이용허락범위 제한 없음 | 2026-10-02 | 192행 (2018~2027) | 조장 |

### 사용 예정 (아직 내려받지 않음)

| 데이터 | 출처 | 라이선스 | 비고 |
|---|---|---|---|
| 고도 | Open-Meteo Elevation API / https://open-meteo.com/en/docs/elevation-api | CC BY 4.0 | 호출 확인 완료 |
| 해안선 | Natural Earth 10m coastline / https://www.naturalearthdata.com/downloads/10m-physical-vectors/10m-coastline/ | 퍼블릭 도메인 | 해안 거리 계산 테스트 완료 |
| 토지피복 (녹지 비율) | ESA WorldCover 2021 v200 / https://esa-worldcover.org | CC BY 4.0 | 타일 다운로드 가능 확인. 녹지 비율 계산은 미테스트 |
| 해외 POI | OpenStreetMap (Overpass API) | ODbL | 공용 서버 504·429 빈번. 캐시 필수 |
| 지역별 방문자수 | 한국관광공사 빅데이터 지역별 방문자수_GW (DataLabService) | 공공누리 | TourAPI와 같은 키. ~~확장 기능용~~ 혼잡도 예측(P1) 학습 데이터. `numOfRows=50000`, 월 단위 요청 시 2018-01~2026-08 전체 104회 (Aside에서 확인, 저장소에는 아직 없음) |

> `.csv`는 `.gitignore` 대상이다. `external/`의 직접 작성한 표 3개도 Git에 올리지 않고 팀 공유 드라이브로 공유한다. 재생성할 수 없으니 잃어버리지 않게 주의한다.
