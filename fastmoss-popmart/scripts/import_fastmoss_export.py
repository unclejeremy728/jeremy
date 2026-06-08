from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from update_popmart_daily import (
    DATA_DIR,
    DOCS_DIR,
    RAW_DIR,
    ROOT,
    ROOM_FIELDS,
    SUMMARY_FIELDS,
    build_summary,
    merge_rooms,
    read_csv,
    room_key,
    safe_float,
    safe_int,
    ts_to_iso,
    write_csv,
    write_json,
)


HEADER_ALIASES = {
    "report_date": [
        "reportdate",
        "date",
        "日期",
        "统计日期",
        "数据日期",
        "直播日期",
    ],
    "region": [
        "region",
        "country",
        "market",
        "国家",
        "地区",
        "区域",
        "市场",
        "站点",
    ],
    "currency": [
        "currency",
        "币种",
        "货币",
    ],
    "room_id": [
        "roomid",
        "liveid",
        "直播间id",
        "直播id",
        "场次id",
    ],
    "seller_id": [
        "sellerid",
        "shopid",
        "storeid",
        "店铺id",
        "商家id",
        "小店id",
    ],
    "seller_name": [
        "sellername",
        "shopname",
        "storename",
        "shop",
        "店铺",
        "店铺名称",
        "商家",
        "商家名称",
        "小店名称",
    ],
    "creator_id": [
        "creatorid",
        "authorid",
        "达人id",
        "主播id",
        "账号id",
    ],
    "creator_unique_id": [
        "creatoruniqueid",
        "uniqueid",
        "username",
        "handle",
        "达人账号",
        "达人唯一id",
        "主播账号",
        "账号",
    ],
    "creator_nickname": [
        "creatornickname",
        "nickname",
        "creator",
        "author",
        "达人",
        "达人昵称",
        "主播",
        "主播昵称",
        "账号昵称",
    ],
    "title": [
        "title",
        "livetitle",
        "直播标题",
        "标题",
        "场次标题",
    ],
    "start_at": [
        "startat",
        "starttime",
        "livestarttime",
        "开始时间",
        "开播时间",
        "直播开始时间",
    ],
    "end_at": [
        "endat",
        "endtime",
        "finish_time",
        "结束时间",
        "下播时间",
        "直播结束时间",
    ],
    "duration_seconds": [
        "duration",
        "durationseconds",
        "直播时长",
        "时长",
    ],
    "gmv": [
        "gmv",
        "成交金额",
        "销售额",
        "总销售额",
        "销售金额",
        "直播gmv",
        "总gmv",
    ],
    "units_sold": [
        "unitssold",
        "sales",
        "sold",
        "销量",
        "总销量",
        "销售件数",
        "售出件数",
        "商品销量",
    ],
    "total_viewers": [
        "totalviewers",
        "viewers",
        "views",
        "观看人数",
        "累计观看",
        "累计观看人次",
        "累计观看人数",
        "直播观看人数",
    ],
    "max_concurrent_viewers": [
        "maxconcurrentviewers",
        "peakviewers",
        "maxonline",
        "最高在线",
        "峰值在线",
        "最高在线人数",
        "峰值在线人数",
    ],
    "followers_added": [
        "followersadded",
        "newfollowers",
        "涨粉",
        "新增粉丝",
        "新增粉丝数",
    ],
    "shares": [
        "shares",
        "sharecount",
        "分享",
        "分享数",
    ],
    "product_count": [
        "productcount",
        "products",
        "商品数",
        "直播商品数",
        "上架商品数",
    ],
    "category": [
        "category",
        "品类",
        "类目",
        "主营类目",
    ],
    "cover_url": [
        "cover",
        "coverurl",
        "image",
        "封面",
        "封面图",
    ],
}

NUMERIC_FIELDS = {
    "gmv",
    "units_sold",
    "total_viewers",
    "max_concurrent_viewers",
    "followers_added",
    "shares",
    "product_count",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Import manually exported FastMoss live room CSV files.")
    parser.add_argument("files", nargs="*", help="CSV files exported from FastMoss. Defaults to imports/*.csv.")
    parser.add_argument("--date", help="Fallback report date in YYYY-MM-DD if the export has no date column.")
    parser.add_argument("--region", default="", help="Fallback region/country if the export has no region column.")
    parser.add_argument("--currency", default="", help="Fallback currency if the export has no currency column.")
    parser.add_argument("--filter-popmart", action="store_true", help="Keep only rows containing POP MART/popmart text.")
    parser.add_argument("--render", action="store_true", help="Rebuild docs/index.html after import.")
    args = parser.parse_args()

    files = [Path(item) for item in args.files] or sorted((ROOT / "imports").glob("*.csv"))
    if not files:
        print("[ERROR] No CSV files found. Put FastMoss exports in imports/ or pass file paths.", file=sys.stderr)
        return 2

    updated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    imported_rows: List[Dict[str, Any]] = []
    raw_batches: List[Dict[str, Any]] = []

    for path in files:
        if not path.exists():
            print(f"[WARN] Missing file: {path}", file=sys.stderr)
            continue
        rows = read_export_csv(path)
        normalized_rows = [
            normalize_export_row(
                row,
                source_path=path,
                fallback_date=args.date,
                fallback_region=args.region,
                fallback_currency=args.currency,
                updated_at=updated_at,
            )
            for row in rows
        ]
        normalized_rows = [row for row in normalized_rows if row]
        if args.filter_popmart:
            normalized_rows = [row for row in normalized_rows if row_contains_popmart(row)]
        imported_rows.extend(normalized_rows)
        raw_batches.append(
            {
                "file": str(path),
                "input_rows": len(rows),
                "imported_rows": len(normalized_rows),
            }
        )

    missing_date_count = sum(1 for row in imported_rows if not row.get("report_date"))
    if missing_date_count:
        print(
            f"[ERROR] {missing_date_count} imported rows have no date. Re-run with --date YYYY-MM-DD.",
            file=sys.stderr,
        )
        return 2

    existing_rooms = read_csv(DATA_DIR / "live_rooms.csv")
    merged_rooms = merge_rooms(existing_rooms, imported_rows)
    merged_rooms.sort(key=lambda row: (row.get("report_date", ""), row.get("start_time", ""), row.get("region", "")))
    write_csv(DATA_DIR / "live_rooms.csv", ROOM_FIELDS, merged_rooms)
    write_csv(DATA_DIR / "daily_summary.csv", SUMMARY_FIELDS, build_summary(merged_rooms, updated_at))

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write_json(
        RAW_DIR / f"manual_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        {
            "updated_at": updated_at,
            "batches": raw_batches,
            "rows": imported_rows,
        },
    )

    if args.render:
        subprocess.check_call([sys.executable, str(ROOT / "scripts" / "build_dashboard.py")])

    print(
        json.dumps(
            {
                "files": len(files),
                "rows_imported": len(imported_rows),
                "rooms_total": len(merged_rooms),
                "dashboard": str(DOCS_DIR / "index.html"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def read_export_csv(path: Path) -> List[Dict[str, str]]:
    text = read_text_with_fallback(path)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(text.splitlines(), dialect=dialect)
    return [{str(k or "").strip(): str(v or "").strip() for k, v in row.items()} for row in reader]


def read_text_with_fallback(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def normalize_export_row(
    row: Dict[str, str],
    *,
    source_path: Path,
    fallback_date: Optional[str],
    fallback_region: str,
    fallback_currency: str,
    updated_at: str,
) -> Dict[str, Any]:
    mapped = map_headers(row)
    start_value = mapped.get("start_at", "")
    end_value = mapped.get("end_at", "")
    start_dt = parse_datetime_value(start_value)
    end_dt = parse_datetime_value(end_value)
    report_date = parse_report_date(mapped.get("report_date", "")) or fallback_date or (
        start_dt.date().isoformat() if start_dt else ""
    )
    start_time = int(start_dt.timestamp()) if start_dt else safe_int(start_value)
    end_time = int(end_dt.timestamp()) if end_dt else safe_int(end_value)
    duration_seconds = parse_duration(mapped.get("duration_seconds", ""))
    if start_time and end_time and not duration_seconds:
        duration_seconds = max(0, end_time - start_time)
    if start_time and duration_seconds and not end_time:
        end_time = start_time + duration_seconds

    room_id = mapped.get("room_id", "")
    region = mapped.get("region", "") or fallback_region
    seller_id = mapped.get("seller_id", "")
    creator_unique_id = mapped.get("creator_unique_id", "")
    title = mapped.get("title", "")

    output = {field: "" for field in ROOM_FIELDS}
    output.update(
        {
            "room_key": room_key(room_id, region, seller_id, creator_unique_id, title, start_time),
            "room_id": room_id,
            "report_date": report_date,
            "source": f"manual_export:{source_path.name}",
            "region": region,
            "currency": mapped.get("currency", "") or fallback_currency,
            "seller_id": seller_id,
            "seller_name": mapped.get("seller_name", ""),
            "creator_id": mapped.get("creator_id", ""),
            "creator_unique_id": creator_unique_id,
            "creator_nickname": mapped.get("creator_nickname", ""),
            "title": title,
            "start_time": str(start_time or ""),
            "start_at": ts_to_iso(start_time) if start_time else start_value,
            "end_time": str(end_time or ""),
            "end_at": ts_to_iso(end_time) if end_time else end_value,
            "duration_seconds": str(duration_seconds or ""),
            "category": mapped.get("category", ""),
            "cover_url": mapped.get("cover_url", ""),
            "updated_at": updated_at,
        }
    )
    for field in NUMERIC_FIELDS:
        output[field] = str(parse_number(mapped.get(field, "")))
    return output


def map_headers(row: Dict[str, str]) -> Dict[str, str]:
    normalized_headers = {normalize_header(header): value for header, value in row.items()}
    mapped: Dict[str, str] = {}
    for canonical, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            key = normalize_header(alias)
            if key in normalized_headers:
                mapped[canonical] = normalized_headers[key]
                break
    return mapped


def normalize_header(value: str) -> str:
    return re.sub(r"[\s_\-:：/（）()【】\\[\\].,，]+", "", str(value or "").lower())


def parse_report_date(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", value)
    if match:
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    try:
        return datetime.fromisoformat(value[:10]).date().isoformat()
    except ValueError:
        return ""


def parse_datetime_value(value: str) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    tzinfo = timezone(timedelta(hours=8))
    tz_match = re.search(r"\(?\s*gmt\s*([+-]\d{1,2})(?::?(\d{2}))?\s*\)?", text, flags=re.IGNORECASE)
    if tz_match:
        hours = int(tz_match.group(1))
        minutes = int(tz_match.group(2) or 0)
        sign = 1 if hours >= 0 else -1
        tzinfo = timezone(timedelta(hours=hours, minutes=sign * minutes))
        text = re.sub(r"\(?\s*gmt\s*[+-]\d{1,2}(?::?\d{2})?\s*\)?", "", text, flags=re.IGNORECASE).strip()
    if re.fullmatch(r"\d{10,13}", text):
        timestamp = int(text[:10])
        return datetime.fromtimestamp(timestamp, timezone.utc)
    text = text.replace("年", "-").replace("月", "-").replace("日", " ")
    text = text.replace("/", "-").replace("T", " ")
    text = re.sub(r"\s+", " ", text).strip()
    patterns = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]
    for pattern in patterns:
        try:
            parsed = datetime.strptime(text[: len(datetime.now().strftime(pattern))], pattern)
            return parsed.replace(tzinfo=tzinfo)
        except ValueError:
            continue
    return None


def parse_duration(value: str) -> int:
    text = str(value or "").strip().lower()
    if not text:
        return 0
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return int(float(text))
    match = re.fullmatch(r"(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?", text)
    if match:
        first, second, third = match.groups()
        if third is None:
            return int(first) * 60 + int(second)
        return int(first) * 3600 + int(second) * 60 + int(third)
    hours = number_before(text, "小时") or number_before(text, "h")
    minutes = number_before(text, "分钟") or number_before(text, "min") or number_before(text, "m")
    seconds = number_before(text, "秒") or number_before(text, "s")
    return int(hours * 3600 + minutes * 60 + seconds)


def number_before(text: str, unit: str) -> float:
    match = re.search(r"([\d.]+)\s*" + re.escape(unit), text)
    return float(match.group(1)) if match else 0.0


def parse_number(value: str) -> float:
    text = str(value or "").strip().lower()
    if not text or text in {"-", "--", "n/a", "null"}:
        return 0.0
    multiplier = 1.0
    if "亿" in text:
        multiplier = 100000000.0
    elif "万" in text or text.endswith("w"):
        multiplier = 10000.0
    elif text.endswith("k"):
        multiplier = 1000.0
    elif text.endswith("m"):
        multiplier = 1000000.0
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if cleaned in {"", "-", "."}:
        return 0.0
    return round(safe_float(cleaned) * multiplier, 4)


def row_contains_popmart(row: Dict[str, Any]) -> bool:
    haystack = " ".join(
        str(row.get(field, ""))
        for field in ("seller_name", "creator_unique_id", "creator_nickname", "title", "category")
    ).lower()
    compact = haystack.replace(" ", "")
    return "pop mart" in haystack or "popmart" in compact


if __name__ == "__main__":
    raise SystemExit(main())
