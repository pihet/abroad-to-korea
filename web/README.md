# web — 화면 (React + TypeScript, Vite)

```bash
npm install
npm run dev     # http://localhost:5173 (API·사진은 FastAPI로 넘긴다. 주소는 web/.env 의 VITE_API_TARGET, 기본 http://localhost:8000)
npm run build   # web/dist → FastAPI가 http://localhost:8000 에서 제공
```

- `src/api.ts` — API 계약 타입 (`app/schemas.py`와 같은 모양). 화면은 이 파일만 통해 서버와 이야기한다.
- `src/App.tsx` — 사진 → 영역 → 장면·조건 → 추천 4단계
- `src/components/` — 단계별 화면, 추천 카드, 12개월 막대 그래프
