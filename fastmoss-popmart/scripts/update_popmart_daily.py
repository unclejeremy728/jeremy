from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from fastmoss_client import FastMossAPIError, FastMossClient


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "popmart_fastmoss.json"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DOCS_DIR = ROOT / "docs"

ROOM_FIELDS = [
    "room_key",
    "room_id",
    "report_date",
    "source",
    "region",
    "currency",
    "seller_id",
    "seller_name",
    "creator_id",
    "creator_unique_id",
    "creator_nickname",
    "title",
    "start_time",
    "start_at",
    "end_time",
    "end_at",
    "duration_seconds",
    "gmv",
    "units_sold",
    "total_viewers",
    "max_concurrent_viewers",
    "followers_added",
    "shares",
    "product_count",
    "category",
    "cover_url",
    "updated_at",
]

SUMMARY_FIELDS = [
    "report_date",
    "region",
    "currency",
    "live_count",
    "shop_count",
    "creator_count",
    "gmv",
    "units_sold",
    "total_viewers",
    "duration_hours",
    "max_concurrent_viewers",
    "followers_added",
    "shares",
    "updated_at",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch POP MART global live room daily data from FastMoss.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD. Defaults to yesterday in configured timezone.")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="Path to config JSON.")
    parser.add_argument("--data-dir", default=str(DATA_DIR), help="Directory for CSV and raw JSON output.")
    parser.add_argument("--render", action="store_true", help="Rebuild docs/index.html after fetching.")
    parser.add_argument("--skip-fetch", action="store_true", help="Only rebuild summaries from existing live_rooms.csv.")
    args = parser.parse_args()

    load_env(ROOT / ".env")
    config = load_config(Path(args.config))
    data_dir = Path(args.data_dir)
    raw_dir = data_dir / "raw"
    docs_dir = ROOT / "docs"
    data_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    tz = configured_timezone(config)
    report_date = args.date or default_report_date(tz)
    start_ts, end_ts = day_bounds(report_date, tz)
    updated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    existing_rooms = read_csv(data_dir / "live_rooms.csv")
    discovered_shops: List[Dict[str, Any]] = []
    fetched_rooms: List[Dict[str, Any]] = []

    if not args.skip_fetch:
        search_config = config.get("search", {})
        try:
            client = FastMossClient(sleep_seconds=float(search_config.get("request_sleep_seconds", 0.25)))
        except FastMossAPIError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 2
        discovered_shops = discover_shops(client, config)
        fetched_rooms.extend(fetch_shop_lives(client, config, discovered_shops, report_date, start_ts, end_ts, updated_at))
        fetched_rooms.extend(fetch_keyword_lives(client, config, report_date, start_ts, end_ts, updated_at))

        raw_payload = {
            "report_date": report_date,
            "timezone": config.get("timezone", {}),
            "start_time": start_ts,
            "end_time": end_ts,
            "updated_at": updated_at,
            "shop_count": len(discovered_shops),
            "room_count": len(fetched_rooms),
            "shops": discovered_shops,
            "rooms": fetched_rooms,
        }
        write_json(raw_dir / f"{report_date}.json", raw_payload)

    merged_rooms = merge_rooms(existing_rooms, fetched_rooms)
    merged_rooms.sort(key=lambda row: (row.get("report_date", ""), row.get("start_time", ""), row.get("region", "")))
    write_csv(data_dir / "live_rooms.csv", ROOM_FIELDS, merged_rooms)

    summary_rows = build_summary(merged_rooms, updated_at)
    write_csv(data_dir / "daily_summary.csv", SUMMARY_FIELDS, summary_rows)

    if args.render:
        subprocess.check_call([sys.executable, str(ROOT / "scripts" / "build_dashboard.py")])

    print(
        json.dumps(
            {
                "report_date": report_date,
                "shops_discovered": len(discovered_shops),
                "rooms_fetched": len(fetched_rooms),
                "rooms_total": len(merged_rooms),
                "dashboard": str(docs_dir / "index.html"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def configured_timezone(config: Dict[str, Any]) -> timezone:
    tz_config = config.get("timezone") or {}
    offset_hours = float(tz_config.get("offset_hours", 8))
    label = str(tz_config.get("label", "Asia/Shanghai"))
    return timezone(timedelta(hours=offset_hours), name=label)


def default_report_date(tz: timezone) -> str:
    return (datetime.now(tz).date() - timedelta(days=1)).isoformat()


def day_bounds(report_date: str, tz: timezone) -> Tuple[int, int]:
    day = date.fromisoformat(report_date)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def discover_shops(client: FastMossClient, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    regions = config.get("regions") or []
    terms = config.get("shop_search_terms") or config.get("brand_terms") or ["POP MART"]
    search_config = config.get("search", {})
    pagesize = int(search_config.get("shop_pagesize", 100))
    max_pages = int(search_config.get("max_shop_pages", 2))
    shops_by_key: Dict[str, Dict[str, Any]] = {}

    for manual in config.get("manual_shops", []):
        if not manual.get("enabled") or not manual.get("seller_id"):
            continue
        normalized = normalize_shop(manual, source="manual")
        shops_by_key[shop_key(normalized)] = normalized

    for region in regions:
        for term in terms:
            payloads = [
                {
                    "keywords": term,
                    "filter": {"region": region},
                    "orderby": [{"field": "day7_gmv", "desc": True}],
                },
                {
                    "keywords": "",
                    "filter": {"region": region, "seller_name": term},
                    "orderby": [{"field": "day7_gmv", "desc": True}],
                },
                {
                    "keywords": "",
                    "filter": {"region": region, "brand_name": term},
                    "orderby": [{"field": "day7_gmv", "desc": True}],
                },
            ]
            for payload in payloads:
                try:
                    for item in client.paged_post("/shop/v1/search", payload, pagesize=pagesize, max_pages=max_pages):
                        if not looks_like_popmart(item, config):
                            continue
                        normalized = normalize_shop(item, region_hint=region, source="shop_search")
                        shops_by_key[shop_key(normalized)] = normalized
                except FastMossAPIError as exc:
                    print(f"[WARN] shop search failed for {region}/{term}: {exc}", file=sys.stderr)

    return sorted(shops_by_key.values(), key=lambda row: (row.get("region", ""), row.get("seller_name", "")))


def fetch_shop_lives(
    client: FastMossClient,
    config: Dict[str, Any],
    shops: Iterable[Dict[str, Any]],
    report_date: str,
    start_ts: int,
    end_ts: int,
    updated_at: str,
) -> List[Dict[str, Any]]:
    search_config = config.get("search", {})
    pagesize = int(search_config.get("live_pagesize", 100))
    max_pages = int(search_config.get("max_live_pages_per_shop", 10))
    rooms: List[Dict[str, Any]] = []

    for shop in shops:
        seller_id = shop.get("seller_id")
        if not seller_id:
            continue
        base_payload = {
            "filter": {"seller_id": seller_id},
            "orderby": [{"field": "start_time", "desc": True}],
        }
        for page in range(1, max_pages + 1):
            payload = copy.deepcopy(base_payload)
            payload["page"] = page
            payload["pagesize"] = pagesize
            try:
                response = client.post("/shop/v1/liveList", payload)
            except FastMossAPIError as exc:
                print(f"[WARN] live list failed for seller_id={seller_id}: {exc}", file=sys.stderr)
                break

            data = response.get("data") or {}
            items = data.get("list") or []
            if not items:
                break

            saw_older = False
            for item in items:
                start_time = safe_int(item.get("start_time"))
                if start_time and start_time < start_ts:
                    saw_older = True
                if start_time and start_ts <= start_time < end_ts:
                    rooms.append(
                        normalize_room(
                            item,
                            source="shop_liveList",
                            report_date=report_date,
                            updated_at=updated_at,
                            region_hint=shop.get("region"),
                            shop=shop,
                        )
                    )

            total = safe_int(data.get("total"))
            has_more = data.get("has_more")
            if saw_older:
                break
            if has_more is False or has_more == 0:
                break
            if total and page * pagesize >= total:
                break

    return rooms


def fetch_keyword_lives(
    client: FastMossClient,
    config: Dict[str, Any],
    report_date: str,
    start_ts: int,
    end_ts: int,
    updated_at: str,
) -> List[Dict[str, Any]]:
    regions = config.get("regions") or []
    terms = config.get("live_search_terms") or config.get("brand_terms") or ["POP MART"]
    search_config = config.get("search", {})
    pagesize = int(search_config.get("live_pagesize", 100))
    max_pages = int(search_config.get("max_live_search_pages_per_region", 3))
    rooms: List[Dict[str, Any]] = []

    for region in regions:
        for term in terms:
            payload = {
                "keywords": term,
                "filter": {
                    "region": region,
                    "start_time": {"min": start_ts, "max": end_ts - 1},
                },
                "orderby": [{"field": "start_time", "desc": True}],
            }
            try:
                for item in client.paged_post("/live/v1/search", payload, pagesize=pagesize, max_pages=max_pages):
                    if not looks_like_popmart(item, config):
                        continue
                    rooms.append(
                        normalize_room(
                            item,
                            source="live_search",
                            report_date=report_date,
                            updated_at=updated_at,
                            region_hint=region,
                        )
                    )
            except FastMossAPIError as exc:
                print(f"[WARN] live search failed for {region}/{term}: {exc}", file=sys.stderr)

    return rooms


def normalize_shop(item: Dict[str, Any], *, source: str, region_hint: str = "") -> Dict[str, Any]:
    seller_id = first_value(item, "seller_id", "shop_id", "id")
    seller_name = first_value(item, "seller_name", "shop_name", "name", "nickname")
    brand_name = first_value(item, "brand_name", "brand")
    return {
        "seller_id": str(seller_id or ""),
        "seller_name": str(seller_name or ""),
        "brand_name": str(brand_name or ""),
        "region": str(first_value(item, "region", "shop_region") or region_hint or ""),
        "source": source,
    }


def normalize_room(
    item: Dict[str, Any],
    *,
    source: str,
    report_date: str,
    updated_at: str,
    region_hint: str = "",
    shop: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    creator = item.get("creator") if isinstance(item.get("creator"), dict) else {}
    shop = shop or {}
    start_time = safe_int(first_value(item, "start_time", "live_start_time"))
    duration = safe_int(first_value(item, "duration", "duration_seconds", "live_duration"))
    end_time = safe_int(first_value(item, "end_time", "finish_time", "live_end_time"))
    if start_time and duration and not end_time:
        end_time = start_time + duration

    seller_id = first_nonempty(first_value(item, "seller_id", "shop_id"), shop.get("seller_id"))
    seller_name = first_nonempty(first_value(item, "seller_name", "shop_name"), shop.get("seller_name"))
    region = first_nonempty(first_value(item, "region", "shop_region"), shop.get("region"), region_hint)
    room_id = str(first_value(item, "room_id", "live_id", "id") or "")
    creator_id = str(first_value(item, "creator_id", "author_id") or creator.get("creator_id") or creator.get("id") or "")
    creator_unique_id = str(first_value(item, "creator_unique_id", "unique_id") or creator.get("unique_id") or "")
    creator_nickname = str(first_value(item, "creator_nickname", "nickname") or creator.get("nickname") or "")
    title = str(first_value(item, "title", "live_title", "name") or "")

    row = {
        "room_key": room_key(room_id, region, seller_id, creator_unique_id, title, start_time),
        "room_id": room_id,
        "report_date": report_date,
        "source": source,
        "region": str(region or ""),
        "currency": str(first_value(item, "currency", "currency_code") or ""),
        "seller_id": str(seller_id or ""),
        "seller_name": str(seller_name or ""),
        "creator_id": creator_id,
        "creator_unique_id": creator_unique_id,
        "creator_nickname": creator_nickname,
        "title": title,
        "start_time": str(start_time or ""),
        "start_at": ts_to_iso(start_time),
        "end_time": str(end_time or ""),
        "end_at": ts_to_iso(end_time),
        "duration_seconds": str(duration or ""),
        "gmv": str(safe_float(first_value(item, "gmv", "total_gmv", "revenue"))),
        "units_sold": str(safe_float(first_value(item, "units_sold", "total_units_sold", "sales"))),
        "total_viewers": str(safe_float(first_value(item, "total_user", "total_user_count", "total_viewer_count", "viewers"))),
        "max_concurrent_viewers": str(safe_float(first_value(item, "max_user_count", "max_online_user_count", "peak_viewers"))),
        "followers_added": str(safe_float(first_value(item, "inc_follower_count", "followers_added"))),
        "shares": str(safe_float(first_value(item, "share_count", "shares"))),
        "product_count": str(safe_float(first_value(item, "product_count", "products_count"))),
        "category": str(first_value(item, "category", "main_category", "main_category_name") or ""),
        "cover_url": str(first_value(item, "cover", "cover_url", "image_url") or ""),
        "updated_at": updated_at,
    }
    return row


def looks_like_popmart(item: Dict[str, Any], config: Dict[str, Any]) -> bool:
    terms = [normalize_text(term) for term in (config.get("brand_terms") or ["POP MART"])]
    values: List[str] = []
    for key in (
        "seller_name",
        "shop_name",
        "name",
        "brand_name",
        "brand",
        "title",
        "live_title",
        "creator_unique_id",
        "creator_nickname",
        "unique_id",
        "nickname",
    ):
        value = item.get(key)
        if value:
            values.append(str(value))
    creator = item.get("creator")
    if isinstance(creator, dict):
        values.extend(str(creator.get(key) or "") for key in ("unique_id", "nickname"))
    normalized = " ".join(normalize_text(value) for value in values)
    compact = normalized.replace(" ", "")
    return any(term and (term in normalized or term.replace(" ", "") in compact) for term in terms)


def normalize_text(value: Any) -> str:
    return str(value or "").lower().replace("-", " ").replace("_", " ").strip()


def room_key(
    room_id: str,
    region: str,
    seller_id: str,
    creator_unique_id: str,
    title: str,
    start_time: int,
) -> str:
    if room_id:
        return f"room:{room_id}"
    return "fallback:" + "|".join(
        [
            normalize_text(region),
            normalize_text(seller_id),
            normalize_text(creator_unique_id),
            normalize_text(title)[:80],
            str(start_time or ""),
        ]
    )


def shop_key(shop: Dict[str, Any]) -> str:
    if shop.get("seller_id"):
        return f"{shop.get('region', '')}:{shop['seller_id']}"
    return f"{shop.get('region', '')}:{normalize_text(shop.get('seller_name'))}"


def first_value(item: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
    return None


def first_nonempty(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return ""


def safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def ts_to_iso(value: int) -> str:
    if not value:
        return ""
    return datetime.fromtimestamp(value, timezone.utc).replace(microsecond=0).isoformat()


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: List[str], rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def merge_rooms(existing: List[Dict[str, Any]], fetched: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for row in existing + fetched:
        key = row.get("room_key") or room_key(
            str(row.get("room_id") or ""),
            str(row.get("region") or ""),
            str(row.get("seller_id") or ""),
            str(row.get("creator_unique_id") or ""),
            str(row.get("title") or ""),
            safe_int(row.get("start_time")),
        )
        normalized = {field: row.get(field, "") for field in ROOM_FIELDS}
        normalized["room_key"] = key
        if key not in merged:
            merged[key] = normalized
            continue
        merged[key] = merge_room_row(merged[key], normalized)
    return list(merged.values())


def merge_room_row(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(old)
    old_sources = {part for part in str(old.get("source", "")).split("+") if part}
    new_sources = {part for part in str(new.get("source", "")).split("+") if part}
    sources = sorted(old_sources | new_sources)
    merged["source"] = "+".join(sources)

    for field in ROOM_FIELDS:
        if field in ("room_key", "source"):
            continue
        old_value = merged.get(field, "")
        new_value = new.get(field, "")
        if not old_value and new_value:
            merged[field] = new_value
        elif field in numeric_room_fields() and safe_float(new_value) and not safe_float(old_value):
            merged[field] = new_value
        elif field == "updated_at" and new_value:
            merged[field] = new_value
    return merged


def numeric_room_fields() -> set:
    return {
        "start_time",
        "end_time",
        "duration_seconds",
        "gmv",
        "units_sold",
        "total_viewers",
        "max_concurrent_viewers",
        "followers_added",
        "shares",
        "product_count",
    }


def build_summary(rows: List[Dict[str, Any]], updated_at: str) -> List[Dict[str, Any]]:
    regional_groups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    global_groups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)

    for row in rows:
        report_date = str(row.get("report_date") or "")
        if not report_date:
            continue
        region = str(row.get("region") or "UNKNOWN")
        currency = str(row.get("currency") or "reported")
        regional_groups[(report_date, region, currency)].append(row)
        global_groups[(report_date, "ALL", "mixed" if currency else "reported")].append(row)

    summary = [summarize_group(key, group, updated_at) for key, group in regional_groups.items()]
    summary.extend(summarize_group(key, group, updated_at) for key, group in global_groups.items())
    summary.sort(key=lambda row: (row["report_date"], row["region"], row["currency"]))
    return summary


def summarize_group(key: Tuple[str, str, str], rows: List[Dict[str, Any]], updated_at: str) -> Dict[str, Any]:
    report_date, region, currency = key
    rooms = {row.get("room_key") for row in rows if row.get("room_key")}
    shops = {row.get("seller_id") or row.get("seller_name") for row in rows if row.get("seller_id") or row.get("seller_name")}
    creators = {
        row.get("creator_id") or row.get("creator_unique_id") or row.get("creator_nickname")
        for row in rows
        if row.get("creator_id") or row.get("creator_unique_id") or row.get("creator_nickname")
    }
    duration_hours = sum(safe_float(row.get("duration_seconds")) for row in rows) / 3600
    return {
        "report_date": report_date,
        "region": region,
        "currency": currency,
        "live_count": len(rooms),
        "shop_count": len(shops),
        "creator_count": len(creators),
        "gmv": round(sum(safe_float(row.get("gmv")) for row in rows), 2),
        "units_sold": round(sum(safe_float(row.get("units_sold")) for row in rows), 2),
        "total_viewers": round(sum(safe_float(row.get("total_viewers")) for row in rows), 2),
        "duration_hours": round(duration_hours, 2),
        "max_concurrent_viewers": round(max((safe_float(row.get("max_concurrent_viewers")) for row in rows), default=0), 2),
        "followers_added": round(sum(safe_float(row.get("followers_added")) for row in rows), 2),
        "shares": round(sum(safe_float(row.get("shares")) for row in rows), 2),
        "updated_at": updated_at,
    }


if __name__ == "__main__":
    raise SystemExit(main())
