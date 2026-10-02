# abroad-to-korea

해외 여행지와 분위기가 비슷한 국내 여행지(시군구·관광지)를 추천하는 웹 서비스 프로토타입이다.

- **분위기 유사도**: 해외 여행지 사진과 국내 관광지 사진을 CLIP 이미지 임베딩으로 비교해 비슷한 시군구를 추천하고, 근거가 되는 관광지 사진을 함께 보여준다.
- **혼잡도 예측**: 시군구별 외지인 방문자 수를 월·일 단위로 예측해 "덜 붐비는" 대안을 고를 수 있게 한다. 연휴 예측을 별도로 보정한다.

교육 과정 팀 프로젝트(2026-10-01 ~ 2026-10-16)의 데이터·모델 프로토타입이며, 진행 기록과 평가 수치는 [`docs/HANDOFF.md`](docs/HANDOFF.md)에 있다.

## 사용 데이터 (공공·공개 데이터)

| 데이터 | 출처 | 용도 |
|---|---|---|
| 국문 관광정보 서비스 (KorService2) | 한국관광공사 / 공공데이터포털 | 국내 관광지 목록·좌표·분류·사진(공공누리 1·3유형) |
| 빅데이터 지역별 방문자수 (DataLabService) | 한국관광공사 / 공공데이터포털 | 시군구별 외지인 방문자 수 (혼잡도 예측) |
| 특일 정보 | 한국천문연구원 / 공공데이터포털 | 공휴일 (연휴 예측) |
| Wikimedia Commons | 사진별 CC BY·CC BY-SA·CC0·퍼블릭 도메인 | 해외 여행지 장면 사진 |
| Open-Meteo, Natural Earth | 각 제공처 | 기후·고도·해안 거리 (검토용) |

데이터 파일 본체는 저장소에 포함하지 않는다. 출처·라이선스·재생성 방법은 [`data/README.md`](data/README.md)에 정리했다.

## 구성

```
src/
  collect/     공공데이터 수집 (관광지 목록, 관광지 추가 이미지, 방문자 수)
  forecast/    혼잡도 예측 (p1_spec: 기준 재현, p1_holiday: 연휴 예측 개선)
  prototype/   CLIP 분위기 유사도 (장면 카탈로그 추천, 평가, 쏠림 보정 실험)
docs/
  HANDOFF.md   진행 기록·평가 결과
data/          (파일 본체는 Git 제외)
```

## 실행

```bash
python -m venv .venv && source .venv/bin/activate
pip install pandas numpy scikit-learn python-dotenv holidays lightgbm
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install transformers pillow

echo "TOUR_API_KEY=<공공데이터포털 인증키>" > .env   # 포털 표시값 그대로 (재인코딩하지 않음)

python src/collect/tour_attractions.py      # 국내 관광지 목록
python src/collect/datalab_visitors.py      # 지역별 방문자 수
python src/forecast/p1_spec.py kasi         # 혼잡도 예측 기준 재현
```

LightGBM 은 Linux/WSL 에서 `sudo apt install -y libgomp1` 이 먼저 필요하다.
검증에 쓴 버전: Python 3.12, pandas 2.2.3, numpy 2.1.3, scikit-learn 1.5.2, holidays 0.105, lightgbm 4.7.0, torch 2.14.1(CPU), transformers 5.18.0.

## 현재 수치 (요약, 자세한 조건은 HANDOFF 참고)

- 분위기 유사도 (CLIP, 개발셋 해외지 23곳): 정답 시군구 Hit@5 57%, Hit@10 74% (랜덤 약 4%·8%)
  - 새 해외지 15곳 파일럿: Hit@10 40% — 도시 장면은 강하고 특정 지점형 정답은 약하다
- 혼잡도 예측 (일 단위, 검증 2025): 전체 WAPE 7.3%, 연휴 관련일 13.2% (기준선 9.9% / 28.2%)
