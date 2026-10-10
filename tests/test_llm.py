import asyncio
import json

import httpx
import app.llm as llm
from app.llm import TripPlanner


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": json.dumps(self.content)}}


class FakeClient:
    def __init__(self, response=None, error=None, **_kwargs):
        self.response = response
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, *_args, **_kwargs):
        if self.error:
            raise self.error
        return FakeResponse(self.response)


def test_ollama_extracts_bounded_travel_intent(monkeypatch):
    response = {"visual_prompt_en": "a quiet beach at sunset", "month": 10, "priority": "near",
                "origin": "부산", "filters": ["sea", "calm", "sea"], "sido": "강원"}
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kwargs: FakeClient(response=response, **kwargs))
    result = asyncio.run(TripPlanner(base_url="http://ollama", model="test").interpret("부산에서 가까운 강원 바다"))
    assert result.used_llm is True
    assert result.intent.sido == "강원특별자치도"
    assert result.intent.origin == "부산" and result.intent.priority == "near"
    assert result.intent.filters == ["sea"]


def test_unstated_example_conditions_are_removed(monkeypatch):
    leaked = {"visual_prompt_en": "a quiet Korean seaside village", "month": None, "priority": "near",
              "origin": "부산", "filters": ["sea", "calm", "rural"], "sido": None}
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kwargs: FakeClient(response=leaked, **kwargs))
    result = asyncio.run(TripPlanner(base_url="http://ollama", model="test").interpret("부산"))
    assert result.used_llm is True
    assert result.intent.sido == "부산광역시"
    assert result.intent.origin is None and result.intent.filters == [] and result.intent.priority == "visual"
    assert result.intent.visual_prompt_en == "a scenic travel destination in South Korea"


def test_ollama_failure_uses_local_fallback(monkeypatch):
    request = httpx.Request("POST", "http://ollama/api/chat")
    error = httpx.ConnectError("offline", request=request)
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kwargs: FakeClient(error=error, **kwargs))
    result = asyncio.run(TripPlanner(base_url="http://ollama", model="test").interpret("부산에서 가까운 조용한 바다"))
    assert result.used_llm is False
    assert result.intent.origin == "부산" and result.intent.priority == "near"
    assert result.intent.filters == ["sea", "calm"]
    assert result.fallback_reason
