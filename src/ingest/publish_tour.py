"""Validate local TourAPI JSON, archive it to MinIO, and idempotently publish normalized rows."""

import argparse
import hashlib
import json
import os
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb
from minio import Minio
from minio.error import S3Error
from redis import Redis

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw/tourapi"
GROUP_NAMES = {
    "water": "물·바다", "mountain": "산·숲", "leisure": "레저", "camping": "캠핑",
    "experience": "체험", "food": "먹거리", "festival": "축제",
}
LEPORTS_EXCLUDE = {"스포츠센터, 수련시설", "스포츠경기장", "수영", "인라인(실내 인라인 포함)"}


def items_from_pages(folder: Path) -> list[dict]:
    rows = []
    for path in sorted(folder.glob("page_*.json")):
        body = json.loads(path.read_text(encoding="utf-8"))["response"]["body"]
        item = (body.get("items") or {}).get("item") or []
        rows.extend(item if isinstance(item, list) else [item])
    return rows


def latest(pattern: str) -> Path | None:
    found = sorted(RAW.glob(pattern))
    return found[-1] if found else None


def region_map() -> dict[tuple[str, str], tuple[str, str, str]]:
    path = latest("ldongCode2_list_*.json")
    if path is None:
        raise RuntimeError("법정동 코드 원본이 없습니다.")
    items = json.loads(path.read_text(encoding="utf-8"))["response"]["body"]["items"]["item"]
    return {(x["lDongRegnCd"], x["lDongSignguCd"]):
            (f'{x["lDongRegnCd"]}_{x["lDongSignguNm"].split()[0]}', x["lDongRegnNm"], x["lDongSignguNm"].split()[0]) for x in items}


def festival_rows() -> tuple[list[dict], Path | None]:
    found = list(RAW.glob("searchFestival2_*.json"))
    if not found:
        return [], None
    def coverage(path: Path) -> tuple[int, str]:
        match = re.search(r"_(\d{8})_(\d{8})$", path.stem)
        return ((datetime.strptime(match[2], "%Y%m%d") - datetime.strptime(match[1], "%Y%m%d")).days, match[2]) if match else (0, path.name)
    path = max(found, key=coverage)
    body = json.loads(path.read_text(encoding="utf-8"))["response"]["body"]
    item = (body.get("items") or {}).get("item") or []
    return (item if isinstance(item, list) else [item]), path


def classification_names() -> dict[str, str]:
    path = latest("lclsSystmCode2_*.json")
    if path is None:
        raise RuntimeError("관광 분류 코드 원본이 없습니다.")
    items = json.loads(path.read_text(encoding="utf-8"))["response"]["body"]["items"]["item"]
    names = {}
    for item in items:
        for level in "123":
            code = item.get(f"lclsSystm{level}Cd")
            if code:
                names[code] = item[f"lclsSystm{level}Nm"]
    return names


def activity_group(ctype: str, row: dict, names: dict[str, str]) -> tuple[str | None, str | None]:
    c2, c3 = row.get("lclsSystm2", ""), row.get("lclsSystm3", "")
    n2, n3 = names.get(c2, ""), names.get(c3, "")
    if ctype == "15":
        return "festival", "축제"
    if ctype == "39":
        return "food", n3 or "음식점"
    if ctype == "28":
        if n3 in LEPORTS_EXCLUDE or not n2:
            return None, None
        if n2 == "캠핑":
            return "camping", n3 or n2
        if n2 == "수상레저스포츠":
            return "water", n3 or n2
        if n2 in ("육상레저스포츠", "항공레저스포츠", "복합레저스포츠", "레저스포츠시설"):
            return "leisure", n3 or n2
        return None, None
    if ctype == "25":
        return None, "여행코스"
    if c2 == "NA02" or n3 == "유람선/잠수함관광":
        return "water", n3 or n2
    if c2 in ("NA01", "NA04"):
        return "mountain", n3 or n2
    if c2.startswith("EX"):
        return "experience", n3 or n2
    return None, n3 or n2 or "관광지"


def place_attributes(ctype: str, row: dict, names: dict[str, str]) -> dict:
    group, kind = activity_group(ctype, row, names)
    attrs = {key: row[key] for key in (
        "lclsSystm1", "lclsSystm2", "lclsSystm3", "firstimage", "firstimage2", "cpyrhtDivCd",
    ) if row.get(key)}
    attrs.update(group=group, kind=kind or GROUP_NAMES.get(group))
    return attrs


def archive(client: Minio, bucket: str, paths: list[Path], logical_date: str, run_id: uuid.UUID, conn) -> None:
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    existing = {row[0] for row in conn.execute("SELECT object_key FROM raw_objects WHERE object_key LIKE 'bronze/tourapi/%'")}
    for path in paths:
        if not path.is_file():
            continue
        data = path.read_bytes()
        digest = hashlib.sha256(data).digest()
        rel = path.relative_to(ROOT / "data/raw")
        key = f"bronze/tourapi/{rel.parent.as_posix()}/{path.stem}/{digest.hex()}.json"
        if key in existing:
            continue
        try:
            client.stat_object(bucket, key)
        except S3Error as exc:
            if exc.code not in ("NoSuchKey", "NoSuchObject"):
                raise
            client.fput_object(bucket, key, str(path), content_type="application/json")
        conn.execute(
            "INSERT INTO raw_objects (id, ingestion_run_id, object_key, sha256, size_bytes) VALUES (%s,%s,%s,%s,%s) "
            "ON CONFLICT (object_key) DO UPDATE SET sha256=EXCLUDED.sha256, size_bytes=EXCLUDED.size_bytes",
            (uuid.uuid4(), run_id, key, digest, len(data)),
        )


def parse_day(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


def parse_float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "", "null") else None
    except (TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logical-date", required=True)
    parser.add_argument("--dag-id", default="tour_data_backfill")
    args = parser.parse_args()
    regions = region_map()
    names = classification_names()
    folders = [(ctype, latest(f"areaBasedList2_ct{ctype}_*")) for ctype in (12, 25, 28, 39)]
    places = [(str(ctype), row) for ctype, folder in folders if folder for row in items_from_pages(folder)]
    festivals, festival_file = festival_rows()
    if not places:
        raise RuntimeError("게시할 관광지 목록이 없습니다.")
    malformed = [row.get("contentid") for _, row in places if not row.get("contentid") or not row.get("title")]
    if malformed:
        raise RuntimeError(f"필수값이 없는 관광지 {len(malformed)}건")

    db_url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    minio = Minio(os.environ["MINIO_ENDPOINT"], access_key=os.environ["MINIO_ACCESS_KEY"],
                  secret_key=os.environ["MINIO_SECRET_KEY"], secure=os.getenv("MINIO_SECURE", "false").lower() == "true")
    bucket = os.getenv("MINIO_BUCKET", "abroad-to-korea")
    logical_date = datetime.fromisoformat(args.logical_date).replace(tzinfo=timezone.utc)
    run_id = uuid.uuid4()
    with psycopg.connect(db_url) as conn:
        source_id = conn.execute(
            "INSERT INTO data_sources (id,key,name,base_url) VALUES (%s,'tourapi','한국관광공사 TourAPI','https://apis.data.go.kr/B551011/KorService2') "
            "ON CONFLICT (key) DO UPDATE SET updated_at=now() RETURNING id", (uuid.uuid4(),)).fetchone()[0]
        existing = conn.execute(
            "SELECT id FROM ingestion_runs WHERE source_id=%s AND dag_id=%s AND logical_date=%s",
            (source_id, args.dag_id, logical_date),).fetchone()
        if existing:
            run_id = existing[0]
            conn.execute("UPDATE ingestion_runs SET status='running', error=NULL, started_at=now(), finished_at=NULL WHERE id=%s", (run_id,))
        else:
            conn.execute("INSERT INTO ingestion_runs (id,source_id,dag_id,logical_date,status,rows_received,rows_published) "
                         "VALUES (%s,%s,%s,%s,'running',0,0)",
                         (run_id, source_id, args.dag_id, logical_date))

        for key, sido, name in sorted(set(regions.values())):
            conn.execute(
                "INSERT INTO regions (key,sido,name,is_active,last_seen_at) VALUES (%s,%s,%s,true,now()) "
                "ON CONFLICT (key) DO UPDATE SET sido=EXCLUDED.sido,name=EXCLUDED.name,is_active=true,last_seen_at=now(),updated_at=now()",
                (key, sido, name),)

        conn.execute("UPDATE places SET is_active=false,updated_at=now() WHERE source_id=%s AND content_type=ANY(%s)",
                     (source_id, [str(ctype) for ctype, _ in folders] + ["15"]))
        conn.execute("UPDATE festivals SET is_active=false,updated_at=now() WHERE source_id=%s", (source_id,))
        place_ids = {}
        for ctype, row in places + [("15", row) for row in festivals]:
            mapped = regions.get((row.get("lDongRegnCd"), row.get("lDongSignguCd")))
            region_key = mapped[0] if mapped else None
            place_id = conn.execute(
                "INSERT INTO places (id,source_id,source_record_id,region_key,content_type,name,address,latitude,longitude,attributes,is_active,last_seen_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,now()) "
                "ON CONFLICT (source_id,source_record_id) DO UPDATE SET region_key=EXCLUDED.region_key,content_type=EXCLUDED.content_type,name=EXCLUDED.name,address=EXCLUDED.address,latitude=EXCLUDED.latitude,longitude=EXCLUDED.longitude,attributes=EXCLUDED.attributes,is_active=true,last_seen_at=now(),updated_at=now() RETURNING id",
                (uuid.uuid4(), source_id, str(row["contentid"]), region_key, ctype, row["title"], row.get("addr1"),
                 parse_float(row.get("mapy")), parse_float(row.get("mapx")),
                 Jsonb(place_attributes(ctype, row, names))),).fetchone()[0]
            place_ids[str(row["contentid"])] = place_id
            if row.get("firstimage"):
                conn.execute("UPDATE place_images SET is_primary=false,updated_at=now() WHERE place_id=%s AND is_primary=true",
                             (place_id,))
                conn.execute(
                    "INSERT INTO place_images (id,place_id,source_url,license_code,is_primary,is_active) VALUES (%s,%s,%s,%s,true,true) "
                    "ON CONFLICT (place_id,source_url) DO UPDATE SET license_code=EXCLUDED.license_code,is_primary=true,is_active=true,updated_at=now()",
                    (uuid.uuid4(), place_id, row["firstimage"], row.get("cpyrhtDivCd")),)

        image_files = [p for name in ("detailImage2", "detailImage2_ct39") for p in (RAW / name).glob("*.json")]
        for path in image_files:
            place_id = place_ids.get(path.stem)
            if place_id is None:
                continue
            body = json.loads(path.read_text(encoding="utf-8"))["response"]["body"]
            rows = (body.get("items") or {}).get("item") or []
            rows = rows if isinstance(rows, list) else [rows]
            for image in rows:
                url = image.get("originimgurl") or image.get("smallimageurl")
                if not url:
                    continue
                conn.execute(
                    "INSERT INTO place_images (id,place_id,source_url,license_code,is_primary,is_active) VALUES (%s,%s,%s,%s,false,true) "
                    "ON CONFLICT (place_id,source_url) DO UPDATE SET license_code=EXCLUDED.license_code,is_active=true,updated_at=now()",
                    (uuid.uuid4(), place_id, url, image.get("cpyrhtDivCd")),)

        intro_files = list((RAW / "detailIntro2_ct39").glob("*.json"))
        for path in intro_files:
            place_id = place_ids.get(path.stem)
            if place_id is None:
                continue
            body = json.loads(path.read_text(encoding="utf-8"))["response"]["body"]
            rows = (body.get("items") or {}).get("item") or []
            row = rows[0] if isinstance(rows, list) and rows else rows if isinstance(rows, dict) else {}
            if row.get("firstmenu"):
                conn.execute("UPDATE places SET attributes=attributes || %s::jsonb,updated_at=now() WHERE id=%s",
                             (Jsonb({"firstmenu": row["firstmenu"]}), place_id))

        common_files = list((RAW / "detailCommon2").glob("*.json"))
        for path in common_files:
            place_id = place_ids.get(path.stem)
            if place_id is None:
                continue
            body = json.loads(path.read_text(encoding="utf-8"))["response"]["body"]
            rows = (body.get("items") or {}).get("item") or []
            row = rows[0] if isinstance(rows, list) and rows else rows if isinstance(rows, dict) else {}
            detail = {key: row[key] for key in ("overview", "homepage", "tel") if row.get(key)}
            if detail:
                conn.execute("UPDATE places SET attributes=attributes || %s::jsonb,updated_at=now() WHERE id=%s",
                             (Jsonb(detail), place_id))

        course_info = list((RAW / "detailInfo2_ct25").glob("*.json"))
        course_intro = {path.stem: path for path in (RAW / "detailIntro2_ct25").glob("*.json")}
        for path in course_info:
            place_id = place_ids.get(path.stem)
            if place_id is None:
                continue
            body = json.loads(path.read_text(encoding="utf-8"))["response"]["body"]
            rows = (body.get("items") or {}).get("item") or []
            rows = rows if isinstance(rows, list) else [rows]
            stops = [{key: row.get(key) for key in ("subnum", "subcontentid", "subname", "subdetailoverview")}
                     for row in rows]
            intro = {}
            if path.stem in course_intro:
                ibody = json.loads(course_intro[path.stem].read_text(encoding="utf-8"))["response"]["body"]
                irows = (ibody.get("items") or {}).get("item") or []
                intro = irows[0] if isinstance(irows, list) and irows else irows if isinstance(irows, dict) else {}
            conn.execute("UPDATE places SET attributes=attributes || %s::jsonb,updated_at=now() WHERE id=%s",
                         (Jsonb({"stops": stops, **{k: intro[k] for k in ("distance", "taketime", "theme") if intro.get(k)}}), place_id))

        for row in festivals:
            mapped = regions.get((row.get("lDongRegnCd"), row.get("lDongSignguCd")))
            if not mapped or not row.get("eventstartdate") or not row.get("eventenddate"):
                continue
            conn.execute(
                "INSERT INTO festivals (id,source_id,source_record_id,place_id,region_key,name,starts_on,ends_on,status,is_active,last_seen_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'scheduled',true,now()) "
                "ON CONFLICT (source_id,source_record_id) DO UPDATE SET region_key=EXCLUDED.region_key,name=EXCLUDED.name,starts_on=EXCLUDED.starts_on,ends_on=EXCLUDED.ends_on,is_active=true,last_seen_at=now(),updated_at=now()",
                (uuid.uuid4(), source_id, str(row["contentid"]), place_ids.get(str(row["contentid"])), mapped[0], row["title"],
                 parse_day(row["eventstartdate"]), parse_day(row["eventenddate"])),)

        archive_paths = [p for _, folder in folders if folder for p in folder.glob("*.json")]
        archive_paths.extend(image_files)
        archive_paths.extend(intro_files)
        archive_paths.extend(common_files)
        archive_paths.extend(course_info)
        archive_paths.extend(course_intro.values())
        if festival_file:
            archive_paths.append(festival_file)
        archive(minio, bucket, archive_paths, args.logical_date, run_id, conn)
        conn.execute("UPDATE ingestion_runs SET status='success',rows_received=%s,rows_published=%s,finished_at=now() WHERE id=%s",
                     (len(places) + len(festivals), len(places) + len(festivals), run_id))
        conn.commit()
    cache = Redis.from_url(os.environ["REDIS_URL"])
    for key in cache.scan_iter("query:*"):
        cache.delete(key)
    cache.set("dataset_version", args.logical_date)
    cache.close()
    print(f"관광 데이터 {len(places)}건, 축제 {len(festivals)}건 게시", flush=True)


if __name__ == "__main__":
    main()
