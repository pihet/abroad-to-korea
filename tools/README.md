# tools

- `record_deck/` — 진행 기록 PPT를 만드는 Node 스크립트 (`cd tools/record_deck && npm install && node build.js <출력 경로.pptx>`)
- `eval_intent.py` — AI 여행 질문 해석 평가 (`tests/data/intent_cases.json` 60문장과 항목별 비교). `--llm`은 Ollama까지 거치는 서비스 경로, `--llm --raw`는 규칙 보정 없는 LLM 출력. 8000번 서버가 떠 있어야 한다
