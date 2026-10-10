"""PostgreSQL-backed TourAPI catalog queries used by the public API."""

import re
from collections import Counter
from datetime import date
from types import SimpleNamespace

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .activities import GROUPS, _menu_words
from .context import haversine
from .models import Festival, Place, PlaceImage, Region
from .search import CHO, _norm, _score

LICENSES = {"Type1": "공공누리 제1유형 (출처표시)", "Type3": "공공누리 제3유형 (출처표시·변경금지)"}


def _image_url(place: Place, image: PlaceImage | None) -> tuple[str | None, str | None]:
    if image is None or image.license_code not in LICENSES:
        return None, None
    return f"/images/tour/{place.source_record_id}", LICENSES[image.license_code]


def _activity(place: Place, image: PlaceImage | None, festival: Festival | None = None) -> dict:
    attrs = place.attributes or {}
    image_url, license_name = _image_url(place, image)
    row = {
        "id": place.source_record_id, "name": place.name, "group": attrs.get("group"),
        "kind": attrs.get("kind") or "관광지", "lat": place.latitude, "lon": place.longitude,
        "address": place.address, "image_url": image_url, "license": license_name,
        "menu": attrs.get("firstmenu"),
    }
    if festival:
        row.update(start=festival.starts_on.strftime("%Y%m%d"), end=festival.ends_on.strftime("%Y%m%d"))
    return row


class Catalog:
    async def _places(self, db: AsyncSession, *, region_key: str | None = None,
                      ids: list[str] | None = None, content_type: str | None = None) -> list[tuple[Place, PlaceImage | None]]:
        primary = and_(PlaceImage.place_id == Place.id, PlaceImage.is_primary.is_(True), PlaceImage.is_active.is_(True))
        query = select(Place, PlaceImage).outerjoin(PlaceImage, primary).where(Place.is_active.is_(True))
        if region_key is not None:
            query = query.where(Place.region_key == region_key)
        if ids is not None:
            if not ids:
                return []
            query = query.where(Place.source_record_id.in_(ids))
        if content_type is not None:
            query = query.where(Place.content_type == content_type)
        return list((await db.execute(query)).all())

    async def activities(self, db: AsyncSession, region_key: str, month: int | None,
                         origin: tuple[float, float] | None = None) -> tuple[list[dict], list[dict]]:
        rows = await self._places(db, region_key=region_key)
        festivals = {f.place_id: f for f in (await db.scalars(select(Festival).where(
            Festival.region_key == region_key, Festival.is_active.is_(True)))).all()}
        out = []
        for place, image in rows:
            item = _activity(place, image, festivals.get(place.id))
            if not item["group"] or item["lat"] is None or item["lon"] is None:
                continue
            if item["group"] == "festival":
                if not item.get("start") or not item.get("end"):
                    continue
                if month is not None and not (item["start"][:6] <= f"2026{month:02d}" <= item["end"][:6]):
                    continue
                item["period"] = f"{_display_day(item['start'])} ~ {_display_day(item['end'])}"
                item["schedule"] = "예정" if item["end"] >= date.today().strftime("%Y%m%d") else "지난 개최 기록"
            item["distance_km"] = round(haversine(origin, (item["lat"], item["lon"])), 1) if origin else None
            out.append({k: v for k, v in item.items() if k not in ("start", "end")})
        out.sort(key=lambda r: (r["distance_km"] if r["distance_km"] is not None else 0, r["name"]))
        counts = Counter(r["group"] for r in out)
        return ([{"key": key, "label": label, "count": counts.get(key, 0)} for key, label in GROUPS], out)

    async def snapshot(self, db: AsyncSession):
        """Small startup snapshot for derived region and neighborhood indexes; PostgreSQL remains the source."""
        rows = await self._places(db)
        festivals = {festival.place_id: festival for festival in (await db.scalars(
            select(Festival).where(Festival.is_active.is_(True)))).all()}
        snapshot = SimpleNamespace(by_region={}, by_id={})
        for place, image in rows:
            item = _activity(place, image, festivals.get(place.id))
            if not item["group"] or item["lat"] is None or item["lon"] is None or place.region_key is None:
                continue
            snapshot.by_id[item["id"]] = item
            snapshot.by_region.setdefault(place.region_key, []).append(item)
        return snapshot

    async def recommendation_records(self, db: AsyncSession) -> list[dict]:
        rows = (await db.execute(select(Place, Region).outerjoin(Region, Region.key == Place.region_key).where(
            Place.content_type == "12", Place.is_active.is_(True)))).all()
        out = []
        for place, region in rows:
            attrs = place.attributes or {}
            out.append({
                "contentid": place.source_record_id, "title": place.name, "addr1": place.address,
                "mapy": place.latitude, "mapx": place.longitude,
                "firstimage": attrs.get("firstimage"), "firstimage2": attrs.get("firstimage2"),
                "cpyrhtDivCd": attrs.get("cpyrhtDivCd"),
                "lclsSystm1": attrs.get("lclsSystm1"), "lclsSystm2": attrs.get("lclsSystm2"),
                "lclsSystm3": attrs.get("lclsSystm3"), "region_key": region.key if region else None,
                "region_code": region.key.split("_", 1)[0] if region else None,
                "region_name": region.name if region else None, "sido": region.sido if region else None,
            })
        return out

    async def festivals(self, db: AsyncSession, start: date, end: date, max_days: int = 62) -> list[dict]:
        query = (select(Festival, Region, Place, PlaceImage)
                 .join(Region, Region.key == Festival.region_key)
                 .outerjoin(Place, Place.id == Festival.place_id)
                 .outerjoin(PlaceImage, and_(PlaceImage.place_id == Place.id, PlaceImage.is_primary.is_(True),
                                             PlaceImage.is_active.is_(True)))
                 .where(Festival.is_active.is_(True), Festival.ends_on >= start, Festival.starts_on <= end,
                        Festival.ends_on - Festival.starts_on < max_days))
        out = []
        for festival, region, place, image in (await db.execute(query)).all():
            image_url, license_name = _image_url(place, image) if place else (None, None)
            out.append({
                "id": festival.source_record_id, "name": festival.name, "region_key": festival.region_key,
                "region": {"key": region.key, "name": region.name, "sido": region.sido},
                "address": place.address if place else None, "image_url": image_url, "license": license_name,
                "start": festival.starts_on.isoformat(), "end": festival.ends_on.isoformat(),
                "starts_in_range": festival.starts_on >= start,
            })
        return sorted(out, key=lambda f: (not f["starts_in_range"], f["start"] if f["starts_in_range"] else f["end"], f["name"]))

    async def food_summary(self, db: AsyncSession, region_key: str, top: int = 8, min_menus: int = 5) -> dict:
        rows = await self._places(db, region_key=region_key, content_type="39")
        menus = [(p.attributes or {}).get("firstmenu") for p, _ in rows]
        menus = [m for m in menus if m]
        counts = Counter()
        for menu in menus:
            counts.update(set(_menu_words(menu)))
        words = [{"name": word, "places": n} for word, n in counts.most_common(top) if n >= 2] if len(menus) >= min_menus else []
        return {"n_places": len(rows), "n_menus": len(menus), "top": words}

    async def counts(self, db: AsyncSession, month: int | None) -> tuple[dict[str, int], dict[str, int]]:
        places = await db.execute(select(Place.region_key, Place.attributes).where(
            Place.is_active.is_(True), Place.latitude.is_not(None), Place.longitude.is_not(None)))
        activity = Counter()
        for region_key, attrs in places:
            if region_key and (attrs or {}).get("group") not in (None, "festival", "food"):
                activity[region_key] += 1
        festival_query = select(Festival.region_key, Festival.starts_on, Festival.ends_on).where(Festival.is_active.is_(True))
        festival = Counter()
        today = date.today()
        for region_key, starts_on, ends_on in (await db.execute(festival_query)).all():
            if region_key and ((month is None and ends_on >= today) or
                               (month is not None and starts_on.strftime("%Y%m") <= f"2026{month:02d}" <= ends_on.strftime("%Y%m"))):
                festival[region_key] += 1
        return dict(activity), dict(festival)

    async def places_by_ids(self, db: AsyncSession, ids: list[str]) -> list[dict]:
        order = {value: i for i, value in enumerate(ids)}
        out = [_activity(place, image) for place, image in await self._places(db, ids=ids)]
        return sorted((row for row in out if row["group"]), key=lambda row: order.get(row["id"], len(order)))

    async def search_places(self, db: AsyncSession, q: str, limit: int = 20) -> list[dict]:
        normalized = _norm(q)
        query = select(Place, Region).join(Region, Region.key == Place.region_key).where(Place.is_active.is_(True))
        if not all(char in CHO for char in normalized):
            query = query.where(Place.name.ilike(f"%{q}%"))
        rows = (await db.execute(query)).all()
        hits = []
        for place, region in rows:
            score = _score(place.name, normalized, all(char in CHO for char in normalized))
            if score:
                attrs = place.attributes or {}
                hits.append((score, {"id": place.source_record_id, "name": place.name,
                                     "kind": attrs.get("kind") or "관광지", "group": attrs.get("group"),
                                     "region_key": region.key, "region_name": region.name, "sido": region.sido,
                                     "dong_code": None, "dong_name": None}))
        hits.sort(key=lambda item: (-item[0], len(item[1]["name"]), item[1]["name"]))
        return [row for _, row in hits[:limit]]

    async def courses(self, db: AsyncSession, region_key: str) -> tuple[list[dict], int, int]:
        courses = list((await db.scalars(select(Place).where(
            Place.content_type == "25", Place.is_active.is_(True)))).all())
        stop_ids = [str(stop.get("subcontentid")) for course in courses for stop in (course.attributes or {}).get("stops", [])
                    if stop.get("subcontentid")]
        stop_rows = {place.source_record_id: {**_activity(place, image), "region": place.region_key}
                     for place, image in await self._places(db, ids=list(set(stop_ids)))}
        out, loaded = [], 0
        for course in courses:
            raw_stops = (course.attributes or {}).get("stops") or []
            if not raw_stops:
                continue
            loaded += 1
            stops, seen = [], set()
            for raw in sorted(raw_stops, key=lambda row: int(row.get("subnum") or 0)):
                content_id = str(raw.get("subcontentid") or "") or None
                identity = content_id or raw.get("subname")
                if not identity or identity in seen:
                    continue
                seen.add(identity)
                place = stop_rows.get(content_id) if content_id else None
                stops.append({
                    "order": len(stops) + 1, "id": content_id, "name": (raw.get("subname") or "").strip(),
                    "overview": clean_html(raw.get("subdetailoverview")),
                    "lat": place["lat"] if place else None, "lon": place["lon"] if place else None,
                    "group": place["group"] if place else None, "kind": place["kind"] if place else None,
                    "image_url": place["image_url"] if place else None, "license": place["license"] if place else None,
                    "region": place["region"] if place else None,
                })
            regions = Counter(stop["region"] for stop in stops if stop["region"])
            if not regions or region_key not in regions:
                continue
            attrs = course.attributes or {}
            out.append({"id": course.source_record_id, "title": course.name, "stops": stops,
                        "distance": attrs.get("distance"), "taketime": attrs.get("taketime"),
                        "theme": attrs.get("theme"), "regions": dict(regions)})
        out.sort(key=lambda course: (-course["regions"][region_key], -len(course["stops"]), course["title"]))
        return out, loaded, len(courses)

    async def primary_image(self, db: AsyncSession, content_id: str, full: bool = False) -> str | None:
        place = await db.scalar(select(Place).where(Place.source_record_id == content_id, Place.is_active.is_(True)))
        if place is None:
            return None
        attrs = place.attributes or {}
        if attrs.get("cpyrhtDivCd") not in LICENSES:
            return None
        return attrs.get("firstimage" if full else "firstimage2") or attrs.get("firstimage")

    async def images(self, db: AsyncSession, content_id: str) -> tuple[Place | None, list[PlaceImage]]:
        place = await db.scalar(select(Place).where(Place.source_record_id == content_id, Place.is_active.is_(True)))
        if place is None:
            return None, []
        images = (await db.scalars(select(PlaceImage).where(
            PlaceImage.place_id == place.id, PlaceImage.is_active.is_(True), PlaceImage.license_code.in_(LICENSES))
            .order_by(PlaceImage.is_primary.desc(), PlaceImage.created_at, PlaceImage.id))).all()
        return place, list(images)


def _display_day(value: str) -> str:
    return f"{value[:4]}.{value[4:6]}.{value[6:]}"


def clean_html(value: str | None) -> str | None:
    cleaned = " ".join(re.sub(r"<[^>]+>", " ", value or "").split())
    return cleaned or None
