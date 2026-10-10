"""Ollama로 자연어 여행 요청을 안전한 추천 조건으로 변환한다."""

import json
import re
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from .settings import get_settings

FilterKey = Literal["sea", "mountain", "calm", "city", "rural", "mild"]
Priority = Literal["visual", "crowd", "near", "season"]
CITY_ORIGINS = ("서울", "부산", "대구", "광주", "대전")  # app/context.py ORIGINS 와 같은 5개 도시

# 시도: 데이터(관광공사 시군구)의 이름. 광주·전남은 2026년 통합 뒤 '전남광주통합특별시' 하나다
SIDOS = (
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "대전광역시", "울산광역시", "세종특별자치시",
    "경기도", "강원특별자치도", "충청북도", "충청남도", "전북특별자치도", "경상북도", "경상남도",
    "제주특별자치도", "전남광주통합특별시",
)
# 사람이 쓰는 이름 → 데이터 시도 이름. 긴 이름부터 찾는다 (강원도 → 강원 순)
SIDO_ALIASES = {
    "광주광역시": "전남광주통합특별시", "전라남도": "전남광주통합특별시", "강원도": "강원특별자치도", "제주도": "제주특별자치도",
    "전라북도": "전북특별자치도", "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "전남광주통합특별시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전북특별자치도", "전남": "전남광주통합특별시", "경북": "경상북도", "경남": "경상남도",
    "제주": "제주특별자치도",
}
SIDO_NAMES = sorted((*SIDOS, *SIDO_ALIASES), key=len, reverse=True)

# 출발지로 알아듣는 시군구 이름 → 시군구 key. 서버가 켜질 때 set_places() 로 채운다 ('수원시'·'수원' → '41_수원시')
PLACES: dict[str, str] = {}


def set_places(region_keys) -> None:
    """시군구 key('41_수원시') 목록으로 출발지 이름표를 만든다. 이름이 겹치는 곳(중구·고성군 등)과 5개 도시 이름은 뺀다."""
    names: dict[str, set] = {}
    for key in region_keys:
        name = key.split("_", 1)[1]
        for alias in {name, name[:-1] if len(name) >= 3 and name[-1] in "시군구" else name}:
            names.setdefault(alias, set()).add(key)
    PLACES.clear()
    PLACES.update({alias: next(iter(keys)) for alias, keys in names.items()
                   if len(keys) == 1 and alias not in CITY_ORIGINS and alias not in SIDO_ALIASES})

# 단어 일부가 잘못 걸리는 것 막기: '산책·산호·산토리니·산들바람'의 산, '섬세·섬진강'의 섬
FILTER_RULES = {
    "sea": r"바다|바닷가|해변|해안|섬(?![세진])|오션",
    "mountain": r"산(?![책호토들업])|숲|계곡|등산|트레킹|단풍",
    "calm": r"조용|한적|한산|붐비지|덜\s*붐|덜\s*북적|북적이지|사람\s*(?:적|없)",
    "city": r"도시|도심|야경|빌딩|번화가",
    "rural": r"시골|농촌|마을|전원",
}
WEATHER = r"날씨|따뜻|시원|쾌적"  # 달이 있을 때만 mild (날씨 조건은 여행 월이 있어야 쓸 수 있다)
CROWD = r"한산|덜\s*붐|덜\s*북적|북적이지|붐비지|사람\s*(?:적|없)"
NEAR = r"가까운|가까이|근처|근교|멀지"
SEASONS = {"봄": 4, "여름": 7, "가을": 10, "겨울": 1}
# 'X 말고', 'X는 싫고', 'X 빼고' 의 X 는 조건에서 뺀다
NEGATION = r"(\S+?)(?:은|는|이|가)?\s*(?:말고|빼고|싫고|싫어|제외|아니고)"


class TravelIntent(BaseModel):
    visual_prompt_en: str = Field(min_length=3, max_length=300, description="원하는 풍경의 구체적인 영어 사진 설명")
    month: int | None = Field(default=None, ge=1, le=12, description="명시된 여행 월")
    priority: Priority = Field(default="visual", description="가장 중요한 정렬 기준")
    origin: str | None = Field(default=None, max_length=40, description="~에서 출발한다고 명시한 도시 또는 시군구")
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
- origin은 사용자가 출발한다고 쓴 도시·시군구 이름만 쓴다.
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
        """원문에서 확인되는 조건만 규칙으로 뽑는다. 평가: tools/eval_intent.py (tests/data/intent_cases.json)."""
        origin = None
        names = "|".join(map(re.escape, sorted((*CITY_ORIGINS, *PLACES), key=len, reverse=True)))
        if m := re.search(rf"({names})(?:시|군|구)?\s*(?:에서|출발|근교|근처)", query):
            origin = m.group(1) if m.group(1) in CITY_ORIGINS else PLACES[m.group(1)]
            query_wo_origin = query[:m.start()] + query[m.end():]  # 출발지 이름은 목적지 시도로 다시 읽지 않는다
        else:
            query_wo_origin = query
        text = query_wo_origin
        for w in re.findall(NEGATION, query_wo_origin):
            text = text.replace(w, " ")
        sido = next((SIDO_ALIASES.get(n, n) for n in SIDO_NAMES if n in text), None)
        for n in SIDO_NAMES:
            text = text.replace(n, " ")
        filters = [key for key, pattern in FILTER_RULES.items() if re.search(pattern, text)]
        month_match = re.search(r"(?<!\d)(1[0-2]|[1-9])\s*월", query)
        month = int(month_match.group(1)) if month_match else next((m for w, m in SEASONS.items() if w in query), None)
        if month and re.search(WEATHER, text):
            filters.append("mild")
        if "city" in filters and "rural" in filters:  # 서로 반대: '도시 말고'처럼 부정을 못 읽은 경우 마을 쪽을 남긴다
            filters.remove("city")
        priority: Priority = "visual"
        if origin and re.search(NEAR, query):
            priority = "near"
        elif re.search(CROWD, text):
            priority = "crowd"
        elif month and re.search(r"날씨|계절|쾌적", text):
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
