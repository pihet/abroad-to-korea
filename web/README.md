# web — 프론트 (React + TypeScript, Vite)

```bash
npm install
npm run dev     # http://localhost:5173 (API·사진은 FastAPI로 넘긴다. 주소는 web/.env 의 VITE_API_TARGET, 기본 http://localhost:8000)
npm run build   # web/dist → FastAPI가 http://localhost:8000 에서 제공 (Docker는 이미지 빌드 때 함께 빌드)
```

| 파일 | 역할 |
|---|---|
| `src/FeedApp.tsx` | 앱 뼈대: 메인 피드(스토리 칩 바다·산숲·시골·도시), 하단 탭, 뒤로가기(history) 처리 |
| `src/FeedExplore.tsx` | 탐색: 해외 사진을 대륙별로 보고 누르면 닮은 국내 여행지 찾기 |
| `src/FeedSearch.tsx` | 사진으로 찾기: 예시 카드 → 사진 올리기 → 결과 |
| `src/FeedRegion.tsx` | 지역 상세: 사진, 예상 경비, 축제·체험, 코스, 음식점, 출처 |
| `src/RegionSearch.tsx` | 이름 검색 |
| `src/AccountModal.tsx` | 로그인·회원가입 (인프라 담당) |
| `src/api.ts` | 서버 호출과 응답 타입 (`app/schemas.py`와 같은 모양) |
| `src/components/` | 코스, 동네 음식점, 지도, 사진 확대, 비 예보, 사진 자르기 |
| `src/styles.css`, `feed.css`, `region.css`, `search.css` | 공통·피드·지역 상세·사진으로 찾기 스타일 |
