"""Ollama로 자연어 여행 요청을 안전한 추천 조건으로 변환한다."""

import json
import re
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from .settings import get_settings

FilterKey = Literal["sea", "mountain", "calm", "city", "rural", "mild"]
Priority = Literal["visual", "crowd", "near", "season"]
Origin = Literal["서울", "부산", "대구", "광주", "대전"]

SIDOS = (
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시",
    "세종특별자치시", "경기도", "강원특별자치도", "충청북도", "충청남도", "전북특별자치도", "전라남도",
    "경상북도", "경상남도", "제주특별자치도", "전남광주통합특별시",
)
SIDO_ALIASES = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
    "제주": "제주특별자치도",
}


class TravelIntent(BaseModel):
    visual_prompt_en: str = Field(min_length=3, max_length=300, description="원하는 풍경의 구체적인 영어 사진 설명")
    month: int | None = Field(default=None, ge=1, le=12, description="명시된 여행 월")
    priority: Priority = Field(default="visual", description="가장 중요한 정렬 기준")
    origin: Origin | None = Field(default=None, description="~에서 출발한다고 명시한 도시")
    filters: list[FilterKey] = Field(default_factory=list, description="명시된 여행 조건만 포함")
    sido: str | None = Field(default=None, description="목적지를 특정 시도로 제한한 경우의 정식 이름")


class IntentResult(BaseModel):
    intent: TravelIntent
    used_llm: bool
    fallback_reason: str | None = None


SYSTEM_PROMPT = """당신은 한국 국내여행 검색 조건 추출기다.
사용자 문장을 설명하거나 장소를 추천하지 말고 JSON만 반환한다.
- visual_prompt_en: 사용자가 원하는 풍경을 CLIP 검색에 쓸 구체적인 영어 사진 설명으로 번역한다.
- filters: sea(바다), mountain(산·숲), calm(방문객 적음), city(도시), rural(시골), mild(해당 월 쾌적한 날씨)만 쓴다.
- priority: visual, crowd, near, season 중 하나다. 가까움을 말하면 near, 덜 붐빔을 가장 중시하면 crowd, 계절 날씨를 가장 중시하면 season이다.
- origin은 서울, 부산, 대구, 광주, 대전 중 명시된 출발지만 쓴다.
- "부산에서", "서울 출발"처럼 쓰면 반드시 origin으로 추출한다. 이때 같은 이름을 sido에 넣지 않는다.
- sido는 사용자가 여행 지역을 제한한 경우에만 대한민국의 정식 시도 이름으로 쓴다.
- month는 명시된 1~12월만 쓰고 추측하지 않는다.
- city와 rural은 서로 반대이므로 동시에 넣지 않는다. "마을"은 rural이고 city가 아니다.
모르는 값은 null 또는 빈 배열로 둔다. 실제 관광지 이름은 만들지 않는다."""

EXAMPLE_USER = "대전에서 가까운 조용한 바닷가 마을에 가고 싶어"
EXAMPLE_ASSISTANT = json.dumps({
    "visual_prompt_en": "a quiet Korean seaside village with a peaceful beach",
    "month": None, "priority": "near", "origin": "대전", "filters": ["sea", "calm", "rural"], "sido": None,
}, ensure_ascii=False)


class TripPlanner:
    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: float | None = None):
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.timeout = timeout or settings.ollama_timeout_seconds

    async def interpret(self, query: str) -> IntentResult:
        payload = {
            "model": self.model,
            "stream": False,
            "format": TravelIntent.model_json_schema(),
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": EXAMPLE_USER},
                {"role": "assistant", "content": EXAMPLE_ASSISTANT},
                {"role": "user", "content": query},
            ],
            "options": {"temperature": 0},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
            content = response.json()["message"]["content"]
            intent = TravelIntent.model_validate(json.loads(content))
            return IntentResult(intent=self._ground(intent, query), used_llm=True)
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError, ValidationError) as exc:
            return IntentResult(intent=self._fallback(query), used_llm=False,
                                fallback_reason=f"Ollama 응답을 사용할 수 없어 기본 해석을 적용했습니다: {type(exc).__name__}")

    @staticmethod
    def _ground(intent: TravelIntent, query: str) -> TravelIntent:
        """LLM이 만든 조건 중 원문에서 확인할 수 없는 값은 추천에 사용하지 않는다."""
        facts = TripPlanner._explicit_facts(query)
        stripped = query
        for name in (*SIDOS, *SIDO_ALIASES):
            stripped = stripped.replace(name, "")
        stripped = re.sub(r"(여행|관광|추천|해줘|가고\s*싶어|찾아줘|으로|로|에|만)", "", stripped)
        visual_prompt = intent.visual_prompt_en
        if not stripped.strip():
            visual_prompt = "a scenic travel destination in South Korea"
        return intent.model_copy(update={"visual_prompt_en": visual_prompt, **facts})

    @staticmethod
    def _explicit_facts(query: str) -> dict:
        keyword_text = query
        for name in (*SIDOS, *SIDO_ALIASES):
            keyword_text = keyword_text.replace(name, "")
        rules = {
            "sea": ("바다", "바닷가", "해변", "해안", "섬", "오션"),
            "mountain": ("산", "숲", "계곡", "등산", "트레킹"),
            "calm": ("조용", "한적", "한산", "붐비지", "사람 적", "북적이지"),
            "city": ("도시", "도심", "야경", "빌딩", "번화가"),
            "rural": ("시골", "농촌", "마을", "전원"),
            "mild": ("날씨", "따뜻", "시원", "쾌적"),
        }
        filters = [key for key, words in rules.items() if any(word in keyword_text for word in words)]
        month_match = re.search(r"(?<!\d)(1[0-2]|[1-9])\s*월", query)
        month = int(month_match.group(1)) if month_match else None
        origin_match = re.search(r"(서울|부산|대구|광주|대전)(?:에서|\s*출발)", query)
        origin = origin_match.group(1) if origin_match else None
        sido = next((name for name in SIDOS if name in query and name != SIDO_ALIASES.get(origin)), None)
        if sido is None:
            sido = next((full for short, full in SIDO_ALIASES.items() if short in query and short != origin), None)
        priority: Priority = "visual"
        if origin and any(word in query for word in ("가까운", "가까이", "근처", "멀지")):
            priority = "near"
        elif any(word in query for word in ("한산", "덜 붐", "사람 적", "북적이지")):
            priority = "crowd"
        elif month and any(word in query for word in ("날씨", "계절", "쾌적")):
            priority = "season"
        return {"month": month, "priority": priority, "origin": origin, "filters": filters, "sido": sido}

    @staticmethod
    def _fallback(query: str) -> TravelIntent:
        facts = TripPlanner._explicit_facts(query)
        filters = facts["filters"]
        visual = [
            label for key, label in {
                "sea": "a peaceful Korean seaside and beach", "mountain": "green mountains and dense forest",
                "calm": "a quiet uncrowded atmosphere", "city": "a lively modern cityscape",
                "rural": "a tranquil rural village", "mild": "pleasant travel weather",
            }.items() if key in filters
        ]
        return TravelIntent(visual_prompt_en=", ".join(visual) or "a scenic travel destination in South Korea",
                            **facts)
