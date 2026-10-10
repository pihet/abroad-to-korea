"""AI 여행 질문 해석 평가: tests/data/intent_cases.json 의 정답과 항목별로 비교한다.

실행:
  .venv/bin/python tools/eval_intent.py            # 규칙만 (Ollama 없이, 빠름)
  .venv/bin/python tools/eval_intent.py --llm      # 서비스와 같은 경로 (Ollama localhost:11434, 문장당 수 초)
  .venv/bin/python tools/eval_intent.py --llm --raw  # 참고: 규칙 보정 없이 LLM 출력만
  .venv/bin/python tools/eval_intent.py --show     # 틀린 문장도 출력
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import urllib.request  # noqa: E402

from app.llm import TripPlanner, set_places  # noqa: E402

FIELDS = ("origin", "month", "sido", "filters", "priority")


async def parse(planner, q, use_llm):
    intent = (await planner.interpret(q)).intent if use_llm else planner._fallback(q)
    d = intent.model_dump()
    d["filters"] = sorted(set(d["filters"]))
    return d


async def main():
    use_llm, show = "--llm" in sys.argv, "--show" in sys.argv
    cases = json.loads((ROOT / "tests/data/intent_cases.json").read_text(encoding="utf-8"))
    with urllib.request.urlopen("http://localhost:8000/api/regions") as r:  # 서버와 같은 시군구 목록 (8000번 Docker 가 떠 있어야 한다)
        set_places([row["key"] for row in json.load(r)["regions"]])
    planner = TripPlanner(base_url="http://localhost:11434")
    if "--raw" in sys.argv:
        planner._ground = lambda intent, q: intent
    print(f"모드: {'LLM 출력만' if '--raw' in sys.argv else 'LLM+규칙 (서비스 경로)' if use_llm else '규칙만'}")
    for split in ("dev", "holdout"):
        hit, full, wrong = {f: 0 for f in FIELDS}, 0, []
        for c in cases[split]:
            got = await parse(planner, c["q"], use_llm)
            bad = [f for f in FIELDS if got[f] != c[f]]
            for f in FIELDS:
                hit[f] += f not in bad
            full += not bad
            if bad:
                wrong.append((c["q"], {f: (got[f], c[f]) for f in bad}))
        n = len(cases[split])
        print(f"[{split} {n}문장] 전부 맞음 {full}/{n} ({full / n:.0%}) · " + " · ".join(f"{f} {hit[f]}/{n}" for f in FIELDS))
        if show:
            for q, diff in wrong:
                print("   ✗", q, " ".join(f"{f}: {g!r}→정답 {e!r}" for f, (g, e) in diff.items()))


if __name__ == "__main__":
    asyncio.run(main())
