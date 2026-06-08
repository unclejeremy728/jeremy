from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from import_fastmoss_export import parse_number, read_text_with_fallback
from update_popmart_daily import DATA_DIR, ROOT


SKU_FIELDS = [
    "rank",
    "period_start",
    "period_end",
    "keyword",
    "product_name",
    "shop_name",
    "region",
    "currency",
    "price",
    "seven_day_sales",
    "seven_day_gmv",
    "total_sales",
    "total_gmv",
    "source",
    "updated_at",
]

HEADER_ALIASES = {
    "product_name": ["商品", "产品", "商品名称", "product", "productname", "sku", "skuname"],
    "shop_name": ["所属店铺", "店铺", "店铺名称", "shop", "shopname", "seller", "sellername"],
    "region": ["国家", "地区", "区域", "country", "region", "market"],
    "currency": ["币种", "货币", "currency"],
    "price": ["售价", "价格", "price", "pricerange"],
    "seven_day_sales": ["近7天销量", "7天销量", "day7sales", "seven_day_sales"],
    "seven_day_gmv": ["近7天销售额", "近7天GMV", "day7gmv", "seven_day_gmv"],
    "total_sales": ["总销量", "销量", "totalsales", "sales"],
    "total_gmv": ["总销售额", "总GMV", "totalgmv", "gmv"],
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Import FastMoss product/SKU exports and keep POP MART top 5.")
    parser.add_argument("files", nargs="*", help="CSV files exported from FastMoss product search or product ranking.")
    parser.add_argument("--period-start", default="", help="Optional period start date, YYYY-MM-DD.")
    parser.add_argument("--period-end", default="", help="Optional period end date, YYYY-MM-DD.")
    parser.add_argument(
        "--keyword",
        default="popmart,pop mart,POP MART",
        help="Comma-separated keywords used to filter products and shops.",
    )
    parser.add_argument(
        "--sort-by",
        default="seven_day_sales",
        choices=["seven_day_sales", "total_sales", "seven_day_gmv", "total_gmv"],
        help="Ranking metric for top 5 SKU products.",
    )
    parser.add_argument("--render", action="store_true", help="Rebuild docs/index.html after import.")
    args = parser.parse_args()

    files = [Path(item) for item in args.files] or sorted((ROOT / "imports").glob("*sku*.csv"))
    if not files:
        print("[ERROR] No SKU CSV files found. Pass files or put *sku*.csv exports in imports/.", flush=True)
        return 2

    keywords = [item.strip() for item in args.keyword.split(",") if item.strip()]
    updated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows: List[Dict[str, str]] = []
    for path in files:
        for row in read_export_csv(path):
            normalized = normalize_row(
                row,
                source=path.name,
                keywords=keywords,
                period_start=args.period_start,
                period_end=args.period_end,
                updated_at=updated_at,
            )
            if normalized:
                rows.append(normalized)

    rows.sort(key=lambda row: metric_value(row, args.sort_by), reverse=True)
    top_rows = rows[:5]
    for index, row in enumerate(top_rows, start=1):
        row["rank"] = str(index)

    output = DATA_DIR / "top_skus.csv"
    write_csv(output, top_rows)

    if args.render:
        import subprocess
        import sys

        subprocess.check_call([sys.executable, str(ROOT / "scripts" / "build_dashboard.py")])

    print(json.dumps({"sku_rows": len(rows), "top_skus": str(output)}, ensure_ascii=False, indent=2))
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


def normalize_row(
    row: Dict[str, str],
    *,
    source: str,
    keywords: List[str],
    period_start: str,
    period_end: str,
    updated_at: str,
) -> Dict[str, str]:
    mapped = map_headers(row)
    haystack = " ".join([mapped.get("product_name", ""), mapped.get("shop_name", "")]).lower()
    compact = haystack.replace(" ", "")
    if keywords and not any(term.lower() in haystack or term.lower().replace(" ", "") in compact for term in keywords):
        return {}

    output = {field: "" for field in SKU_FIELDS}
    output.update(
        {
            "period_start": period_start,
            "period_end": period_end,
            "keyword": ",".join(keywords),
            "product_name": mapped.get("product_name", ""),
            "shop_name": mapped.get("shop_name", ""),
            "region": mapped.get("region", ""),
            "currency": mapped.get("currency", ""),
            "price": mapped.get("price", ""),
            "seven_day_sales": mapped.get("seven_day_sales", ""),
            "seven_day_gmv": mapped.get("seven_day_gmv", ""),
            "total_sales": mapped.get("total_sales", ""),
            "total_gmv": mapped.get("total_gmv", ""),
            "source": f"manual_sku_export:{source}",
            "updated_at": updated_at,
        }
    )
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
    return re.sub(r"[\s_\-:：/（）()【】\[\].,，]+", "", str(value or "").lower())


def metric_value(row: Dict[str, str], field: str) -> float:
    value = parse_number(row.get(field, ""))
    if value:
        return value
    fallback = "total_sales" if field == "seven_day_sales" else "seven_day_sales"
    return parse_number(row.get(fallback, ""))


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SKU_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in SKU_FIELDS})


if __name__ == "__main__":
    raise SystemExit(main())
