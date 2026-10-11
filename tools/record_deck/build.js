// 미니프로젝트2 진행 기록 PPT. 과제 개요서(미니프로젝트2 개요서.pptx)의 항목 순서를 따른다.
// 실행: node build.js <출력 경로.pptx>
// 수치·상태는 아래 R 에만 적는다. 작업이 바뀌면 R 을 고치고 다시 실행한다 (근거: docs/HANDOFF.md, 테스트 결과).
const path = require('path')
const pptxgen = require('pptxgenjs')

const SKILL_THEME = process.env.APPLY_THEME_JS // pptx 스킬의 apply_theme.js (없으면 테마 색 적용을 건너뜀)

const R = {
  asOf: '2026-10-11',
  name: 'pickkorea',
  tagline: '해외 여행지 사진으로 분위기가 닮은 국내 여행지를 찾는 웹서비스',
  period: '2026.10.01 ~ 2026.10.16',
  repo: 'github.com/pihet/abroad-to-korea',
  tests: 64,
  data: [ // [데이터, 출처, 크기, 쓰임]
    ['관광지 목록·대표사진', '한국관광공사 TourAPI', '12,567곳 · 검색 사진 11,352장', '사진 유사도 검색'],
    ['관광지 추가 사진', 'TourAPI detailImage2', '53,832장 (수집 완료)', '사진 보기 (검색 풀 확대는 미채택)'],
    ['레포츠 · 축제', 'TourAPI', '3,742곳 · 883건', '지역 활동 지도 · 이번 주 축제'],
    ['음식점 · 대표메뉴', 'TourAPI', '13,400곳 · 메뉴 13,261곳', '동네 먹거리'],
    ['공식 여행코스', 'TourAPI 여행코스', '1,068개 (구성 모두 받음)', '지역 상세 코스'],
    ['외지인 방문자 수', '한국관광공사 관광 빅데이터', '시군구 · 2018-01 ~ 2026-08', '혼잡도 예측 학습'],
    ['날씨', 'Open-Meteo', '230개 시군구 일별 (2021~2025) + 16일 예보', '여행 날짜 비 예보'],
    ['여행 경비', '국민여행조사 2023~2025', '관광 여행 59,514건', '지역 1박 예상 경비'],
    ['주민등록 인구', '행정안전부', '읍면동 4,112곳 (2026-09)', '도시 / 시골 구분'],
    ['경계 · 해안선', 'SGIS(admdongkor) · Natural Earth', '행정동 3,558개 · 해안선', '동네 지도 · 바다 여부'],
    ['해외 예시 사진', 'Wikimedia Commons', '383장 (사진별 라이선스)', '질의 예시 · 평가'],
  ],
  stats: [ // [큰 숫자, 설명]
    ['61%', '개발 해외지 38곳 Hit@10 (23곳)\n(정답 시군구가 상위 10곳 안)'],
    ['40%', '처음 본 해외지 15곳 Hit@10\n(새 목적지에서 낮아짐)'],
    ['80%', '사람 평가 1위 후보 "그럴듯함"\n(1명 평가, 상위 5곳 전체는 69%)'],
    ['5.6%', '방문자 예측 WAPE (월 단위, 2025 검증)\n전년 같은 달 기준선 7.7%'],
  ],
}

const THEME = {
  name: 'pickkorea', headFontFace: 'Malgun Gothic', bodyFontFace: 'Malgun Gothic',
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
    ['데이터 활용', '공개 데이터 11종 수집·전처리 (관광지·방문자·날씨·경비·인구·경계·여행코스 등)', '다음 장 데이터 표'],
    ['모델 개발', 'CLIP 사진 유사도 vote100 vs 개선안 5가지(쏠림 보정·카테고리·관광지 단위·큰 모델·사진 6배) 비교, 모두 미채택 / 방문자 예측: 전년 기준선 vs ridge(월)', 'HANDOFF 7·10·11장, 15-26'],
    ['서비스 연결', '사진·AI 질문 → 분석 → 결과 피드 → 지역 상세, 로그인·개인 맞춤 (FastAPI + React, Docker)', `테스트 ${R.tests}개 통과`],
    ['결과 설명', '시각 순위·유사도·조건 근거를 카드에 따로 표시, 성능과 한계를 문서화', '성능 장표, HANDOFF 15장'],
  ], { colW: [1.9, 7.6, 2.63], fontSize: 14, rowH: 0.78 })
}

// ---- 4. 데이터
{
  const sl = slide('2. 수행 목표', '데이터 계획', '모두 공개 데이터이며, 사진은 공공누리 1·3유형과 Commons 라이선스만 쓴다')
  table(sl, ['데이터', '출처', '크기', '쓰임'], R.data, { y: 1.75, colW: [2.3, 3.2, 4.4, 2.23], fontSize: 12, rowH: 0.42 })
}

// ---- 5. 수행 단계 현황
sec('3. 수행 단계')
{
  const sl = slide('3. 수행 단계', '3. 수행 단계 진행 현황', `${R.asOf} 기준`)
  table(sl, ['단계', '상태', '내용'], [
    ['1. 기획', status('완료'), '사용자·문제 정의, 핵심 기능 결정, 기획서 초안과 수정안'],
    ['2. 데이터', status('완료'), '목록·통계·날씨·인구·경계·추가 사진·대표메뉴·여행코스 수집 완료. Airflow가 매일 자정 직후 자동 갱신'],
    ['3. 학습', status('완료'), '개발셋 / 처음 본 해외지(홀드아웃) 분리, 혼잡도는 시간 순서 분할'],
    ['4. 평가', status('진행 중'), 'Hit@k·MRR·WAPE 측정, 개선안 5가지 사전 기준으로 판정, 사람 평가 1명 → 조원 추가 평가 예정'],
    ['5. 구현', status('완료'), '사진·AI 질문·검색 → 결과 피드 → 지역 상세, 로그인·MY·개인 맞춤·문의, 다크 모드·홈 화면 앱(PWA)'],
    ['6. 검증', status('진행 중'), `자동 테스트 ${R.tests}개 통과, 화면 브라우저 점검, 출시 점검(포트·요청 제한·약관·라이선스). 발표·시연 준비 예정`],
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
  sl.addText('개선안 5가지(쏠림 보정·카테고리 재정렬·관광지 단위·큰 모델·국내 사진 6배)는 결과 전에 정한 기준(Hit@10 +4곳·MRR 상승)을 넘지 못해 쓰지 않았다. 병목은 모델 크기보다 데이터와 정답 성격(특정 지점형). 사람 평가는 조원 2~3명으로 늘린다.',
    { x: M, y: 5.5, w: W - 2 * M, h: 0.9, fontSize: 14, color: SUB, isTextBox: true, margin: 0 })
}

// ---- 7. 서비스 구현 범위
sec('4. 서비스 구현 범위')
{
  const sl = slide('4. 서비스 구현 범위', '4. 서비스 구현 범위', '사용자가 사진을 넣으면 모델이 닮은 국내 후보를 내고, 화면이 근거와 함께 보여 준다')
  const cols = [
    ['입력 화면', ['사진 올리기·촬영 (아이폰 HEIC 포함), 찾을 영역 드래그', '탐색 탭: 해외 예시 사진 격자', 'AI 여행: 문장으로 조건 묻기', '지역·동네·장소 이름 검색 (초성 포함)']],
    ['예측 처리', ['CLIP 임베딩 → 관광지별 최고 1장', '상위 100곳을 시군구별로 합산 → 30곳', '질문 해석: Ollama(qwen2.5 3B) + 규칙', '다른 사용자 반응·내 취향으로 30곳 안 순서만 조정']],
    ['결과 화면', ['인스타그램형 피드: 후보 ↔ 내 사진 비교', '지역 상세: 혼잡도, 비 예보, 예상 경비', '동네 지도·음식점, 공식 여행코스, 축제', '장소 정보: 주소·이용 시간·전화·지도']],
  ]
  const cw = (W - 2 * M - 2 * 0.35) / 3
  cols.forEach(([h, items], i) => {
    const x = M + i * (cw + 0.35)
    sl.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.85, w: cw, h: 4.3, fill: { color: SOFT }, line: { color: SOFT }, rectRadius: 0.12, objectName: `col-${i}` })
    sl.addText(h, { x: x + 0.3, y: 2.05, w: cw - 0.6, h: 0.5, fontSize: 20, bold: true, color: ACC, isTextBox: true, margin: 0 })
    sl.addText(items.map((t, j) => ({ text: t, options: { bullet: true, breakLine: j < items.length - 1 } })),
      { x: x + 0.3, y: 2.7, w: cw - 0.6, h: 3.2, fontSize: 15, color: INK, paraSpaceAfter: 10, valign: 'top', isTextBox: true, margin: 0 })
  })
  sl.addText('개발 순서: 사진 추천 핵심 → 지역 정보 → 인스타그램형 디자인 → 코스·축제·검색 → 로그인·개인 맞춤·AI 여행 → 출시 점검', { x: M, y: 6.35, w: W - 2 * M, h: 0.45, fontSize: 14, color: SUB, isTextBox: true, margin: 0 })
}

// ---- 7-1. 10/8 이후 추가한 기능
{
  const sl = slide('4. 서비스 구현 범위', '10/8 이후 추가한 기능', '사진 추천 핵심은 그대로 두고, 사용자 기능과 운영 준비를 채웠다')
  table(sl, ['묶음', '내용', '근거'], [
    ['로그인·MY', '이메일·Google·카카오 가입, 저장한 곳, 반응 목록, 기본 출발지(시군구), 프로필 사진, 문의하기', 'HANDOFF 15-30~33, 15-40'],
    ['재정렬', '내 취향(좋아요·별로예요·저장 3개 이상)과 같은 사진의 다른 사용자 반응으로 30곳 안 순서만 조정', '15-29, 15-35'],
    ['AI 여행', '문장 질문 → Ollama + 규칙으로 조건 해석. 평가 문장 60개 (같은 사람이 써서 독립 평가 아님)', '15-34'],
    ['데이터 운영', 'Airflow 매일 자정 직후 자동 수집 (작업이 실패하던 원인 5가지 해결), 검색 기록 저장', '15-36~37, 15-41'],
    ['출시 점검', '내부 포트 닫기, 요청 횟수 제한, 약관·개인정보처리방침·가입 동의, 기록 보관 기한, PWA 아이콘, 라이선스 점검', '15-42~47'],
  ], { colW: [1.9, 7.6, 2.63], fontSize: 14, rowH: 0.8 })
}

// ---- 8. 아키텍처
{
  const sl = slide('4. 서비스 구현 범위', '시스템 아키텍처', '컨테이너로 나눠 실제로 운영 중이다. 화면과 API는 한 서버(8000번)에서 나간다')
  const box = (x, y, w, h, t, s, hi) => {
    sl.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: hi ? 'E6F1EF' : 'FFFFFF' }, line: { color: hi ? ACC : 'B8C0C4', width: hi ? 2 : 1 }, rectRadius: 0.1, objectName: `box-${t}` })
    sl.addText([{ text: t, options: { bold: true, fontSize: 15, breakLine: true } }, { text: s, options: { fontSize: 12, color: SUB } }],
      { x, y, w, h, align: 'center', valign: 'middle', color: INK, isTextBox: true, margin: 4 })
  }
  const arrow = (x1, y1, x2, y2) => sl.addShape(pres.shapes.LINE, { x: x1, y: y1, w: x2 - x1, h: y2 - y1, line: { color: '8A9499', width: 1.25, endArrowType: 'triangle' } })
  box(M, 2.0, 2.3, 0.9, '사용자', '브라우저 · 홈 화면 앱')
  arrow(M + 2.3, 2.45, M + 2.8, 2.45)
  box(M + 2.8, 2.0, 2.5, 0.9, '터널', 'cloudflared · HTTPS')
  arrow(M + 5.3, 2.45, M + 5.8, 2.45)
  box(M + 5.8, 2.0, 6.33, 0.9, 'api (8000번)', 'FastAPI + React 화면 · CLIP 후보 30곳 · 재정렬 · 요청 제한', true)
  const sw = 1.45, sg = (6.33 - 4 * sw) / 3
  ;[['postgres', '회원·관광지·기록'], ['redis', '세션·캐시·횟수'], ['minio', '프로필·보관 사진'], ['ollama', 'AI 질문 해석']].forEach(([t, d], i) => {
    const x = M + 5.8 + i * (sw + sg)
    box(x, 3.4, sw, 0.9, t, d)
    arrow(x + sw / 2, 2.9, x + sw / 2, 3.4)
  })
  box(M + 5.8, 4.8, 4.0, 1.0, 'airflow', '매일 자정 직후 TourAPI 수집 · 사진·개인정보 정리')
  arrow(M + 6.5, 4.8, M + 6.5, 4.3)
  box(M + 10.0, 4.8, 2.13, 1.0, 'email-worker', 'Resend 메일')
  box(M, 4.8, 4.9, 1.0, '공공데이터 API', 'TourAPI · 관광 빅데이터 · 행정안전부 · Open-Meteo')
  arrow(M + 4.9, 5.3, M + 5.8, 5.3)
  sl.addText('Docker Compose 컨테이너 10개를 PC 한 대에서 실행. 외부에는 8000번만 열고 DB·Redis 등은 PC 안에서만 접속 (MLflow는 실험 기록용).',
    { x: M, y: 6.15, w: W - 2 * M, h: 0.5, fontSize: 14, color: SUB, isTextBox: true, margin: 0 })
}

// ---- 9. 일정
sec('5. 진행 일정')
{
  const sl = slide('5. 진행 일정', '5. 권장 일정 대비 실제 진행', '구현과 출시 점검까지 마쳤고, 남은 기간은 평가와 발표 준비에 쓴다')
  table(sl, ['권장 일정', '권장 내용', '실제 진행'], [
    ['1~2일차', '주제·역할·데이터·기획서', '주제 검증, 데이터 확인, 기획서 초안 (10/1~10/2)'],
    ['3~4일차', '데이터 전처리, 기준 모델', 'CLIP 기준 모델·평가, 혼잡도 기준선 재현·개선 (10/2~10/4)'],
    ['5~7일차', '모델 개선, 화면·예측 개발', 'MVP, 조건 필터, 동네 지도·먹거리 (10/4~10/6) → 인스타그램형 화면, 비 예보, 공식 코스, 축제·검색 (10/7)'],
    ['8~9일차', '통합·테스트·오류 수정', '추가 사진 재평가(미채택), 로그인·MY·개인 맞춤, AI 여행, Airflow 자동 수집 복구, 코드 리뷰 수정, 출시 점검 (10/8~10/11)'],
    ['10일차', '최종 검증·제출물·발표', '예정: 발표자료·시연 영상·코드 압축 (발표 10/16)'],
  ], { colW: [1.7, 3.6, 6.83], rowH: 0.78 })
}

// ---- 10. 기획서 필수항목
sec('6. 최종 제출물')
{
  const sl = slide('6. 최종 제출물', '6. 기획서 필수항목 대응', '기획서 수정안(Claude Docs)과 저장소 문서에 항목별로 들어 있다')
  table(sl, ['필수항목', '현재 내용', '위치'], [
    ['1. 프로젝트 개요', '프로젝트명·기간·주제·목표 (팀명/팀원 기입 필요)', '기획서 1장'],
    ['2. 배경·필요성', '2026년 환율·추석 여행·국내여행 지출 등 기사·보고서 5건 인용', '수행계획서 1장'],
    ['3. 데이터 계획', '출처·크기·쓰임 10종', '수행계획서 3장'],
    ['4. 주요 기능', '사진 검색·조건·결과 피드·지역 상세(혼잡도·비 예보·동네·코스·축제)', '수행계획서 3장'],
    ['5. 서비스 개발 계획', 'CLIP vote100, Hit@k·MRR·WAPE, 아키텍처', '기획서 7~9장'],
    ['6. 개발 계획', 'FastAPI·React·Airflow 등, 일정 (역할 기입 필요)', '기획서 10장'],
    ['7. 기대 효과', '탐색 부담 감소, 덜 알려진 지역 노출 (검증 전)', '기획서 11장'],
  ], { colW: [2.6, 6.2, 3.33], fontSize: 14, rowH: 0.62 })
}

// ---- 11. 제출물 현황
{
  const sl = slide('6. 최종 제출물', '최종 제출물 준비 현황', '기획서와 코드는 준비됐고, 발표자료와 시연이 남았다')
  const cards = [
    ['프로젝트 기획서', '완료 · 다듬는 중', ['수행계획서(docx) 10/7 갱신: 기사 인용 5건 (이후 기능 반영 필요)', '유사 서비스 PICTRIP과 차별점 정리 필요', '팀명·역할 기입 필요']],
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
    '발표자료: 정확도 실험은 개선안 5가지와 미채택 이유를 그대로 보여 준다',
    '시연 시나리오와 백업 영상 (사진 검색 → 지역 상세 → AI 여행)',
    '조원 사람 평가, 탐색 사진 반응 100개 이상 → 만족도 지표',
    '수행계획서에 10/8 이후 기능 반영, 팀명·역할 기입, 코드 ZIP 정리',
    '남은 이슈: 대표 사진에 실내 사진 섞임(#29), 상업 출시 라이선스(#34)',
  ]
  items.forEach((t, i) => {
    const y = 1.8 + i * 1.0
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
