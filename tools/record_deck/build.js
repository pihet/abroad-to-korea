// 미니프로젝트2 진행 기록 PPT. 과제 개요서(미니프로젝트2 개요서.pptx)의 항목 순서를 따른다.
// 실행: node build.js <출력 경로.pptx>
// 수치·상태는 아래 R 에만 적는다. 작업이 바뀌면 R 을 고치고 다시 실행한다 (근거: docs/HANDOFF.md, 테스트 결과).
const path = require('path')
const pptxgen = require('pptxgenjs')

const SKILL_THEME = process.env.APPLY_THEME_JS // pptx 스킬의 apply_theme.js (없으면 테마 색 적용을 건너뜀)

const R = {
  asOf: '2026-10-06',
  name: '닮은꼴 국내 여행지',
  tagline: '해외 여행지 사진으로 분위기가 닮은 국내 여행지를 찾는 웹서비스',
  period: '2026.10.01 ~ 2026.10.16',
  repo: 'github.com/pihet/abroad-to-korea',
  tests: 27,
  data: [ // [데이터, 출처, 크기, 쓰임]
    ['관광지 목록·대표사진', '한국관광공사 TourAPI', '12,603곳 · 임베딩 사진 11,353장', '사진 유사도 검색'],
    ['관광지 추가 사진', 'TourAPI detailImage2', '4,950 / 12,603곳 (매일 수집 중)', '검색 사진 풀 확대'],
    ['레포츠 · 축제', 'TourAPI', '3,751곳 · 883건', '지역 활동 지도'],
    ['음식점 · 대표메뉴', 'TourAPI', '13,402곳 · 메뉴 990곳 (수집 중)', '먹거리'],
    ['외지인 방문자 수', '한국관광공사 관광 빅데이터', '시군구 · 2018-01 ~ 2026-08', '혼잡도·예측 학습'],
    ['날씨', 'Open-Meteo', '230개 시군구 × 12개월 (5년 평균)', '월별 기온·비'],
    ['주민등록 인구', '행정안전부', '읍면동 4,112곳 (2026-09)', '도시 / 시골 구분'],
    ['경계 · 해안선', 'SGIS(admdongkor) · Natural Earth', '행정동 3,558개 · 해안선', '동네 지도 · 바다 여부'],
    ['해외 예시 사진', 'Wikimedia Commons', '383장 (사진별 라이선스)', '질의 예시 · 평가'],
  ],
  stats: [ // [큰 숫자, 설명]
    ['74%', '개발 해외지 23곳 Hit@10\n(정답 시군구가 상위 10곳 안)'],
    ['40%', '처음 본 해외지 15곳 Hit@10\n(새 목적지에서 낮아짐)'],
    ['80%', '사람 평가 1위 후보 "그럴듯함"\n(1명 평가, 상위 5곳 전체는 69%)'],
    ['7.3%', '혼잡도 예측 WAPE (2025 검증)\n기준선 9.9%'],
  ],
}

const THEME = {
  name: '닮은꼴', headFontFace: 'Malgun Gothic', bodyFontFace: 'Malgun Gothic',
  colors: { dk1: '15181A', lt1: 'FFFFFF', dk2: '0A6E66', lt2: 'F4F5F6', accent1: '0A6E66', accent2: 'B5522B', accent3: '2F80D1',
            accent4: 'E0A21A', accent5: '8E4EC6', accent6: '5D6468', hlink: '0A6E66', folHlink: '5D6468' },
}
const INK = THEME.colors.dk1, SUB = '5D6468', ACC = THEME.colors.accent1, SOFT = 'F4F5F6', LINE = 'E4E7E9'

const pres = new pptxgen()
pres.layout = 'LAYOUT_WIDE' // 13.33 × 7.5
pres.title = `${R.name} 진행 기록`
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace }
const W = 13.33, M = 0.6

pres.defineSlideMaster({
  title: 'TITLE', background: { color: INK },
  objects: [{ placeholder: { options: { name: 'title', type: 'title', x: M, y: 2.3, w: W - 2 * M, h: 1.4, fontSize: 44, bold: true, color: 'FFFFFF' }, text: '' } },
            { placeholder: { options: { name: 'body', type: 'body', x: M, y: 3.8, w: W - 2 * M, h: 1.6, fontSize: 18, color: 'C9D1CE' }, text: '' } }],
})
pres.defineSlideMaster({
  title: 'CONTENT', background: { color: 'FFFFFF' },
  objects: [{ placeholder: { options: { name: 'title', type: 'title', x: M, y: 0.35, w: W - 2 * M, h: 0.8, fontSize: 30, bold: true, color: INK, valign: 'middle' }, text: '' } },
            { text: { text: `${R.name} · 진행 기록 · ${R.asOf} 기준`, options: { x: M, y: 7.0, w: 8, h: 0.3, fontSize: 10, color: SUB } } }],
  slideNumber: { x: W - M - 0.6, y: 7.0, w: 0.6, h: 0.3, fontSize: 10, color: SUB, align: 'right' },
})

const sec = t => pres.addSection({ title: t })
const slide = (s, title, lead) => {
  const sl = pres.addSlide({ masterName: 'CONTENT', sectionTitle: s })
  sl.addText(title, { placeholder: 'title' })
  if (lead) sl.addText(lead, { x: M, y: 1.15, w: W - 2 * M, h: 0.5, fontSize: 16, color: SUB, isTextBox: true, margin: 0 })
  return sl
}
// 표: 머리줄 진한 글자 + 옅은 바탕, 본문 행 사이 얇은 선
const table = (sl, head, rows, opt) => {
  const hdr = head.map(h => ({ text: h, options: { bold: true, color: INK, fill: { color: SOFT } } }))
  sl.addTable([hdr, ...rows.map(r => r.map((c, i) => (typeof c === 'object' ? c : { text: c, options: i === 0 ? { bold: true } : {} })))], {
    x: M, y: opt.y ?? 1.8, w: W - 2 * M, colW: opt.colW, fontSize: opt.fontSize ?? 14, color: INK, valign: 'middle',
    border: { type: 'solid', pt: 0.75, color: LINE }, margin: [4, 8, 4, 8], rowH: opt.rowH,
  })
}
const status = s => ({ text: s, options: { bold: true, color: s === '완료' ? ACC : s === '진행 중' ? 'B5522B' : SUB } })

// ---- 1. 표지
sec('표지')
{
  const sl = pres.addSlide({ masterName: 'TITLE', sectionTitle: '표지' })
  sl.addText(R.name, { placeholder: 'title' })
  sl.addText(`${R.tagline}\n미니프로젝트2 진행 기록 · ${R.asOf} 기준`, { placeholder: 'body' })
}

// ---- 2. 프로젝트 개요
sec('1. 프로젝트 개요')
{
  const sl = slide('1. 프로젝트 개요', '1. 프로젝트 개요', '보고 싶은 해외 장면을 사진으로 넣으면, 분위기가 닮은 국내 시군구와 관광지를 찾아 준다')
  table(sl, ['항목', '내용'], [
    ['프로젝트명', R.name],
    ['기간', `${R.period} (10일)`],
    ['팀명 / 팀원', '(작성 필요)'],
    ['주제', '해외 여행지 사진 기반 분위기 유사 국내 여행지 추천'],
    ['주요 목표', '사진 유사도(머신러닝)로 국내 후보를 찾고, 방문객·거리·지역 정보로 비교해 고르게 한다'],
    ['코드', R.repo],
  ], { y: 1.9, colW: [2.4, W - 2 * M - 2.4], rowH: 0.62 })
}

// ---- 3. 수행 목표 대응
sec('2. 수행 목표')
{
  const sl = slide('2. 수행 목표', '2. 수행 목표 대응', '개요서의 다섯 목표를 프로젝트에서 무엇으로 채웠는지')
  table(sl, ['목표', '우리 프로젝트에서 한 것', '근거'], [
    ['문제 정의', '해외 풍경을 좋아하지만 비용·시간이 부담인 사용자에게 국내 대안을 사진으로 찾게 한다', '기획서 2~4장'],
    ['데이터 활용', '공공데이터 9종 수집·전처리 (관광지·방문자·날씨·인구·경계 등)', '다음 장 데이터 표'],
    ['모델 개발', 'CLIP 사진 유사도 vote100 vs 무작위·관광지 단위·카테고리 보정 비교 / 혼잡도: 전년 기준선 vs 회귀·LightGBM', 'HANDOFF 7·10·11장'],
    ['서비스 연결', '사진 업로드 → 분석 → 추천 카드·지도 (FastAPI + React)', `테스트 ${R.tests}개 통과`],
    ['결과 설명', '시각 순위·유사도·조건 근거를 카드에 따로 표시, 성능과 한계를 문서화', '성능 장표, HANDOFF 15장'],
  ], { colW: [1.9, 7.6, 2.63], fontSize: 14, rowH: 0.78 })
}

// ---- 4. 데이터
{
  const sl = slide('2. 수행 목표', '데이터 계획', '모두 공개 데이터이며, 사진은 공공누리 1·3유형과 Commons 라이선스만 쓴다')
  table(sl, ['데이터', '출처', '크기', '쓰임'], R.data, { y: 1.75, colW: [2.3, 3.2, 4.4, 2.23], fontSize: 12, rowH: 0.5 })
}

// ---- 5. 수행 단계 현황
sec('3. 수행 단계')
{
  const sl = slide('3. 수행 단계', '3. 수행 단계 진행 현황', `${R.asOf} 기준`)
  table(sl, ['단계', '상태', '내용'], [
    ['1. 기획', status('완료'), '사용자·문제 정의, 핵심 기능 결정, 기획서 초안과 수정안'],
    ['2. 데이터', status('진행 중'), '목록·통계·날씨·인구·경계 수집 완료. 관광지 추가 사진과 음식점 대표메뉴는 하루 한도로 매일 수집'],
    ['3. 학습', status('완료'), '개발셋 / 처음 본 해외지(홀드아웃) 분리, 혼잡도는 시간 순서 분할'],
    ['4. 평가', status('진행 중'), 'Hit@k·MRR·WAPE 측정, 사람 평가 1명 완료 → 조원 추가 평가 예정'],
    ['5. 구현', status('완료'), '입력(사진·영역·조건) → 예측 → 결과(카드·지도·지역 상세) 연결'],
    ['6. 검증', status('진행 중'), `자동 테스트 ${R.tests}개 통과, 화면 흐름 브라우저 점검. 발표·시연 준비 예정`],
  ], { colW: [1.8, 1.3, 9.03], rowH: 0.72 })
}

// ---- 6. 성능
{
  const sl = slide('3. 수행 단계', '모델 성능 (지금까지)', '정답 지표는 하한에 가깝다. 정답 시군구 외에도 분위기가 닮은 곳이 있기 때문')
  const cw = (W - 2 * M - 3 * 0.35) / 4
  R.stats.forEach(([big, label], i) => {
    const x = M + i * (cw + 0.35)
    sl.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.9, w: cw, h: 3.2, fill: { color: SOFT }, line: { color: SOFT }, rectRadius: 0.12, objectName: `stat-${i}` })
    sl.addText(big, { x: x + 0.25, y: 2.15, w: cw - 0.5, h: 1.3, fontSize: 54, bold: true, color: i === 1 ? 'B5522B' : ACC, isTextBox: true, margin: 0 })
    sl.addText(label, { x: x + 0.25, y: 3.55, w: cw - 0.5, h: 1.4, fontSize: 14, color: INK, isTextBox: true, margin: 0, valign: 'top' })
  })
  sl.addText('한계: 처음 본 해외지와 도시 장면에서 약하다. 관광지 추가 사진(매일 수집)으로 사진 풀을 넓힌 뒤 다시 평가한다. 사람 평가는 조원 2~3명으로 늘린다.',
    { x: M, y: 5.5, w: W - 2 * M, h: 0.9, fontSize: 14, color: SUB, isTextBox: true, margin: 0 })
}

// ---- 7. 서비스 구현 범위
sec('4. 서비스 구현 범위')
{
  const sl = slide('4. 서비스 구현 범위', '4. 서비스 구현 범위', '사용자가 사진을 넣으면 모델이 닮은 국내 후보를 내고, 화면이 근거와 함께 보여 준다')
  const cols = [
    ['입력 화면', ['사진 올리기·촬영 (아이폰 HEIC 포함)', '찾을 영역 드래그', '예시 해외 사진 383장', '조건: 바다·산·방문객·도시/시골·시도']],
    ['예측 처리', ['학습 때와 같은 전처리 (회전 보정·자르기)', 'CLIP 임베딩 → 관광지별 최고 1장', '상위 100곳을 시군구별로 합산 → 30곳', '조건은 후보를 고르기 전에 거른다']],
    ['결과 화면', ['원본·후보 사진을 나란히', '목록 + 전국 지도 (번호 연동)', '월평균 방문·가장 한산한 달·12개월 그래프', '지역 상세: 동네 Top 5, 동네를 누르면 음식점·대표메뉴']],
  ]
  const cw = (W - 2 * M - 2 * 0.35) / 3
  cols.forEach(([h, items], i) => {
    const x = M + i * (cw + 0.35)
    sl.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.85, w: cw, h: 4.3, fill: { color: SOFT }, line: { color: SOFT }, rectRadius: 0.12, objectName: `col-${i}` })
    sl.addText(h, { x: x + 0.3, y: 2.05, w: cw - 0.6, h: 0.5, fontSize: 20, bold: true, color: ACC, isTextBox: true, margin: 0 })
    sl.addText(items.map((t, j) => ({ text: t, options: { bullet: true, breakLine: j < items.length - 1 } })),
      { x: x + 0.3, y: 2.7, w: cw - 0.6, h: 3.2, fontSize: 15, color: INK, paraSpaceAfter: 10, valign: 'top', isTextBox: true, margin: 0 })
  })
  sl.addText('개발 우선순위: 사진 추천 핵심 → 조건 필터 → 지역 정보(활동·먹거리) → 디자인 순으로 완성', { x: M, y: 6.35, w: W - 2 * M, h: 0.45, fontSize: 14, color: SUB, isTextBox: true, margin: 0 })
}

// ---- 8. 아키텍처
{
  const sl = slide('4. 서비스 구현 범위', '시스템 아키텍처', '지금은 FastAPI 한 프로세스. 시연·운영용으로 컨테이너를 나누는 구조를 설계했다')
  const box = (x, y, w, h, t, s, hi) => {
    sl.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: hi ? 'E6F1EF' : 'FFFFFF' }, line: { color: hi ? ACC : 'B8C0C4', width: hi ? 2 : 1 }, rectRadius: 0.1, objectName: `box-${t}` })
    sl.addText([{ text: t, options: { bold: true, fontSize: 15, breakLine: true } }, { text: s, options: { fontSize: 12, color: SUB } }],
      { x, y, w, h, align: 'center', valign: 'middle', color: INK, isTextBox: true, margin: 4 })
  }
  const arrow = (x1, y1, x2, y2) => sl.addShape(pres.shapes.LINE, { x: x1, y: y1, w: x2 - x1, h: y2 - y1, line: { color: '8A9499', width: 1.25, endArrowType: 'triangle' } })
  box(M, 2.0, 2.3, 0.9, '사용자', '브라우저')
  arrow(M + 2.3, 2.45, M + 2.8, 2.45)
  box(M + 2.8, 2.0, 2.5, 0.9, 'web', 'nginx · React')
  arrow(M + 5.3, 2.45, M + 5.8, 2.45)
  box(M + 5.8, 2.0, 2.8, 0.9, 'backend', 'FastAPI · 필터·재정렬')
  arrow(M + 8.6, 2.3, M + 9.1, 2.3); arrow(M + 9.1, 2.6, M + 8.6, 2.6)
  box(M + 9.1, 2.0, 3.0, 0.9, 'model', 'CLIP · 사진→벡터·후보 30곳', true)
  box(M + 5.8, 3.4, 2.8, 0.9, 'redis', '분석 결과 캐시 · 피드백')
  box(M + 9.1, 3.4, 3.0, 0.9, 'postgres', '관광지·통계·피드백')
  arrow(M + 7.2, 2.9, M + 7.2, 3.4); arrow(M + 8.0, 2.9, M + 9.4, 3.4)
  box(M + 5.8, 4.8, 6.3, 1.0, 'airflow', '매일 사진·메뉴 수집 · 매월 방문자·인구·재학습 · 인덱스 재생성')
  arrow(M + 10.6, 4.8, M + 10.6, 4.3)
  box(M, 4.8, 4.9, 1.0, '공공데이터 API', 'TourAPI · 관광 빅데이터 · 행정안전부 · Open-Meteo')
  arrow(M + 4.9, 5.3, M + 5.8, 5.3)
  sl.addText('Docker Compose로 한 대에서 실행(개발·시연). 운영 시 화면은 CDN, redis·postgres는 관리형, 파일은 S3로 분리.',
    { x: M, y: 6.15, w: W - 2 * M, h: 0.5, fontSize: 14, color: SUB, isTextBox: true, margin: 0 })
}

// ---- 9. 일정
sec('5. 진행 일정')
{
  const sl = slide('5. 진행 일정', '5. 권장 일정 대비 실제 진행', '구현은 일정보다 앞서 있고, 남은 기간은 평가와 발표 준비에 쓴다')
  table(sl, ['권장 일정', '권장 내용', '실제 진행'], [
    ['1~2일차', '주제·역할·데이터·기획서', '주제 검증, 데이터 확인, 기획서 초안 (10/1~10/2)'],
    ['3~4일차', '데이터 전처리, 기준 모델', 'CLIP 기준 모델·평가, 혼잡도 기준선 재현·개선 (10/2~10/4)'],
    ['5~7일차', '모델 개선, 화면·예측 개발', 'MVP 웹서비스, 조건 필터, 활동·동네 지도, 먹거리, 디자인 개편 (10/4~10/6)'],
    ['8~9일차', '통합·테스트·오류 수정', '예정: 조원 사람 평가, 추가 사진 반영 재평가, 오류 수정'],
    ['10일차', '최종 검증·제출물·발표', '예정: 발표자료·시연 영상·코드 압축 (발표 10/16)'],
  ], { colW: [1.7, 3.6, 6.83], rowH: 0.78 })
}

// ---- 10. 기획서 필수항목
sec('6. 최종 제출물')
{
  const sl = slide('6. 최종 제출물', '6. 기획서 필수항목 대응', '기획서 수정안(Claude Docs)과 저장소 문서에 항목별로 들어 있다')
  table(sl, ['필수항목', '현재 내용', '위치'], [
    ['1. 프로젝트 개요', '프로젝트명·기간·주제·목표 (팀명/팀원 기입 필요)', '기획서 1장'],
    ['2. 배경·필요성', '2026년 환율·추석 여행·국내여행 지출 기사 근거', '기획서 2장'],
    ['3. 데이터 계획', '출처·크기·쓰임 9종', '기획서 7.4장'],
    ['4. 주요 기능', '사진 검색·조건 필터·추천 카드·지도·지역 상세', '기획서 6장'],
    ['5. 서비스 개발 계획', 'CLIP vote100, Hit@k·MRR·WAPE, 아키텍처', '기획서 7~9장'],
    ['6. 개발 계획', 'FastAPI·React·Airflow 등, 일정 (역할 기입 필요)', '기획서 10장'],
    ['7. 기대 효과', '탐색 부담 감소, 덜 알려진 지역 노출 (검증 전)', '기획서 11장'],
  ], { colW: [2.6, 6.2, 3.33], fontSize: 14, rowH: 0.62 })
}

// ---- 11. 제출물 현황
{
  const sl = slide('6. 최종 제출물', '최종 제출물 준비 현황', '기획서와 코드는 준비됐고, 발표자료와 시연이 남았다')
  const cards = [
    ['프로젝트 기획서', '완료 · 다듬는 중', ['Google Docs 초안', '수정안: 2026 근거 기사·데이터 표·Dupe Finder 비교 반영', '팀명·역할 기입 필요']],
    ['서비스 코드', '완료 · 매일 갱신', ['GitHub 저장소 (전처리·학습·예측·서비스)', `자동 테스트 ${R.tests}개 통과`, '제출 전 ZIP 압축 (데이터·키 제외)']],
    ['발표자료', '예정', ['프로젝트 소개·데이터·모델·성능', '서비스 설명·시연·개발 과정', '시연 영상은 업로드 제외']],
  ]
  const cw = (W - 2 * M - 2 * 0.35) / 3
  cards.forEach(([h, st, items], i) => {
    const x = M + i * (cw + 0.35)
    sl.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.85, w: cw, h: 4.4, fill: { color: SOFT }, line: { color: SOFT }, rectRadius: 0.12, objectName: `card-${i}` })
    sl.addText(h, { x: x + 0.3, y: 2.05, w: cw - 0.6, h: 0.5, fontSize: 20, bold: true, color: INK, isTextBox: true, margin: 0 })
    sl.addText(st, { x: x + 0.3, y: 2.6, w: cw - 0.6, h: 0.4, fontSize: 14, bold: true, color: i === 2 ? SUB : ACC, isTextBox: true, margin: 0 })
    sl.addText(items.map((t, j) => ({ text: t, options: { bullet: true, breakLine: j < items.length - 1 } })),
      { x: x + 0.3, y: 3.2, w: cw - 0.6, h: 2.8, fontSize: 15, color: INK, paraSpaceAfter: 10, valign: 'top', isTextBox: true, margin: 0 })
  })
}

// ---- 12. 다음 할 일
{
  const sl = slide('6. 최종 제출물', '남은 일', `발표(10/16)까지`)
  const items = [
    '조원 2~3명 사람 평가 → 평가자 간 일치도, 엉뚱함 10% 이하 확인',
    '관광지 추가 사진·음식점 대표메뉴 수집 완료 후 인덱스 재생성과 재평가',
    '서버 안정화: 재시작해도 결과 유지(redis), 새 데이터 자동 반영 (이슈 #2·#3)',
    '발표자료·시연 시나리오, 기획서 팀명·역할 기입, 코드 ZIP 정리',
  ]
  items.forEach((t, i) => {
    const y = 1.9 + i * 1.1
    sl.addShape(pres.shapes.OVAL, { x: M, y, w: 0.6, h: 0.6, fill: { color: ACC }, line: { color: ACC }, objectName: `num-${i}` })
    sl.addText(String(i + 1), { x: M, y, w: 0.6, h: 0.6, fontSize: 18, bold: true, color: 'FFFFFF', align: 'center', valign: 'middle', isTextBox: true, margin: 0 })
    sl.addText(t, { x: M + 0.9, y: y - 0.05, w: W - 2 * M - 0.9, h: 0.7, fontSize: 18, color: INK, valign: 'middle', isTextBox: true, margin: 0 })
  })
}

const out = path.resolve(process.argv[2] || 'record.pptx')
pres.writeFile({ fileName: out }).then(async () => {
  if (SKILL_THEME) await require(SKILL_THEME).applyTheme(out, THEME)
  console.log('저장:', out)
})
