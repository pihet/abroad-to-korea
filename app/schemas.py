"""API 계약 (docs/MVP_PLAN.md 5장). 프론트(web/src/api.ts)의 타입과 같은 모양을 유지한다."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

Priority = Literal["visual", "crowd", "near", "season"]
Origin = Literal["서울", "부산", "대구", "광주", "대전"]


class Crop(BaseModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    w: float = Field(gt=0)
    h: float = Field(gt=0)


class Tag(BaseModel):
    tag: str
    score: float


class AnalyzeResponse(BaseModel):
    is_example: bool = False
    query_id: str
    scene_tags: list[Tag]
    image: dict


class RecommendRequest(BaseModel):
    query_id: str
    travel_month: int = Field(ge=1, le=12)
    priority: Priority = "visual"
    origin: Optional[Origin] = None
    kept_tags: Optional[list[str]] = None
    limit: int = Field(default=5, ge=1, le=30)
    offset: int = Field(default=0, ge=0, le=29)


class MonthPoint(BaseModel):
    month: str
    visitors: int
    index: int


class Congestion(BaseModel):
    month: int
    index: int
    visitors: int
    basis: Literal["forecast", "actual"]
    basis_month: str
    monthly: list[MonthPoint]


class Climate(BaseModel):
    month: int
    temp_c: float
    rain_days: float
    comfort: float


class Attraction(BaseModel):
    id: str
    name: str
    address: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    image_url: str
    license: str
    source: str


class Candidate(BaseModel):
    rank: int
    visual_rank: int
    sigungu: dict
    attraction: Attraction
    visual: dict
    similar_tags: list[str]
    different_tags: list[str]
    congestion: Optional[Congestion]
    climate: Optional[Climate]
    distance_km: Optional[int]
    map_links: dict
    rerank: dict


class RecommendResponse(BaseModel):
    is_example: bool = False
    query: dict
    model: dict
    total_candidates: int
    candidates: list[Candidate]
    data_sources: list[dict]


class Feedback(BaseModel):
    query_id: str
    sigungu_key: str
    attraction_id: str
    value: Literal[1, -1]
