from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"


def main() -> int:
    rooms = read_csv(DATA_DIR / "live_rooms.csv")
    summary = read_csv(DATA_DIR / "daily_summary.csv")
    top_skus = read_csv(DATA_DIR / "top_skus.csv")
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    html = render_html(rooms, summary, top_skus, generated_at)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")
    print(str(DOCS_DIR / "index.html"))
    return 0


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def json_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def render_html(
    rooms: List[Dict[str, str]],
    summary: List[Dict[str, str]],
    top_skus: List[Dict[str, str]],
    generated_at: str,
) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>POP MART FastMoss 全球直播日度趋势</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --surface: #ffffff;
      --surface-strong: #f0f4f8;
      --text: #17202a;
      --muted: #697586;
      --line: #d9e1ea;
      --blue: #2563eb;
      --teal: #0f9f8f;
      --orange: #e07a2f;
      --red: #d64550;
      --shadow: 0 14px 30px rgba(20, 29, 38, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.45;
    }}
    header {{
      background: var(--surface);
      border-bottom: 1px solid var(--line);
      position: sticky;
      top: 0;
      z-index: 10;
    }}
    .wrap {{
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
    }}
    .topbar {{
      min-height: 72px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
    }}
    h1 {{
      margin: 0;
      font-size: 21px;
      font-weight: 760;
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
    }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--surface-strong);
      padding: 5px 10px;
      white-space: nowrap;
    }}
    main {{
      padding: 22px 0 36px;
    }}
    .toolbar {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 16px;
      align-items: start;
      margin-bottom: 16px;
    }}
    .segmented {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      min-height: 38px;
    }}
    .segmented button,
    .region-filter label {{
      border: 1px solid var(--line);
      background: var(--surface);
      color: var(--text);
      border-radius: 8px;
      min-height: 34px;
      padding: 7px 10px;
      cursor: pointer;
      font: inherit;
      font-size: 13px;
    }}
    .segmented button.active {{
      border-color: rgba(37, 99, 235, 0.45);
      background: rgba(37, 99, 235, 0.11);
      color: #0f3a8a;
      font-weight: 700;
    }}
    .region-filter {{
      display: flex;
      justify-content: flex-end;
      flex-wrap: wrap;
      gap: 6px;
      max-width: 520px;
    }}
    .region-filter input {{
      margin: 0 6px 0 0;
      vertical-align: -2px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}
    .kpi {{
      min-height: 112px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .kpi .label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
    }}
    .kpi .value {{
      font-size: 28px;
      font-weight: 780;
      line-height: 1.1;
      overflow-wrap: anywhere;
    }}
    .kpi .sub {{
      color: var(--muted);
      font-size: 12px;
    }}
    .panel {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 16px;
      margin-bottom: 16px;
    }}
    .panel-head {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 16px;
      margin-bottom: 12px;
    }}
    h2 {{
      margin: 0;
      font-size: 16px;
    }}
    .hint {{
      color: var(--muted);
      font-size: 12px;
    }}
    .charts {{
      display: grid;
      grid-template-columns: minmax(0, 1.45fr) minmax(280px, 0.75fr);
      gap: 16px;
    }}
    canvas {{
      width: 100%;
      height: 320px;
      display: block;
    }}
    .table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    table {{
      width: 100%;
      min-width: 980px;
      border-collapse: collapse;
      background: var(--surface);
    }}
    th,
    td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      white-space: nowrap;
      font-size: 13px;
    }}
    th {{
      background: var(--surface-strong);
      color: #314156;
      font-weight: 720;
      position: sticky;
      top: 0;
    }}
    td.title-cell {{
      max-width: 280px;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .sku-table table {{
      min-width: 1120px;
    }}
    .sku-product {{
      max-width: 360px;
      white-space: normal;
      min-width: 260px;
    }}
    .rank {{
      font-weight: 780;
      color: #0f3a8a;
    }}
    .empty {{
      min-height: 300px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--muted);
      border: 1px dashed var(--line);
      border-radius: 8px;
      background: var(--surface);
    }}
    @media (max-width: 900px) {{
      .topbar,
      .toolbar,
      .charts {{
        grid-template-columns: 1fr;
        display: grid;
      }}
      .meta,
      .region-filter {{
        justify-content: flex-start;
      }}
      .grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
    @media (max-width: 560px) {{
      .wrap {{
        width: min(100% - 20px, 1180px);
      }}
      .grid {{
        grid-template-columns: 1fr;
      }}
      h1 {{
        font-size: 18px;
      }}
      .kpi .value {{
        font-size: 24px;
      }}
      canvas {{
        height: 260px;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap topbar">
      <h1>POP MART FastMoss 全球直播日度趋势</h1>
      <div class="meta">
        <span class="pill" id="latestDate">最新日期：-</span>
        <span class="pill">直播间口径：popmart + pop mart</span>
        <span class="pill">生成时间：{generated_at}</span>
      </div>
    </div>
  </header>
  <main class="wrap">
    <section class="toolbar">
      <div class="segmented" id="metricButtons"></div>
      <div class="region-filter" id="regionFilter"></div>
    </section>
    <section class="grid" id="kpis"></section>
    <section class="panel">
      <div class="panel-head">
        <h2>日度趋势</h2>
        <span class="hint">GMV 为 FastMoss 返回口径，跨币种区域请按地区拆看</span>
      </div>
      <div id="chartContent" class="charts">
        <canvas id="trendChart" width="900" height="320" aria-label="日度趋势"></canvas>
        <canvas id="regionChart" width="420" height="320" aria-label="区域对比"></canvas>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head">
        <h2>销售前五 SKU 产品</h2>
        <span class="hint" id="skuHint">等待 SKU 导出</span>
      </div>
      <div class="table-wrap sku-table">
        <table>
          <thead>
            <tr>
              <th>排名</th>
              <th>产品</th>
              <th>店铺</th>
              <th>区域</th>
              <th>价格</th>
              <th>近7天销量</th>
              <th>近7天销售额</th>
              <th>总销量</th>
              <th>总销售额</th>
              <th>数据来源</th>
            </tr>
          </thead>
          <tbody id="skuRows"></tbody>
        </table>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head">
        <h2>全量直播间明细</h2>
        <span class="hint" id="roomCount">0 场</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>日期</th>
              <th>区域</th>
              <th>店铺</th>
              <th>达人</th>
              <th>标题</th>
              <th>开始时间 UTC</th>
              <th>币种</th>
              <th>GMV</th>
              <th>销量</th>
              <th>观看</th>
              <th>峰值在线</th>
            </tr>
          </thead>
          <tbody id="roomRows"></tbody>
        </table>
      </div>
    </section>
  </main>
  <script>
    const ROOMS = {json_script(rooms)};
    const SUMMARY = {json_script(summary)};
    const TOP_SKUS = {json_script(top_skus)};
    const METRICS = [
      {{ key: "gmv", label: "GMV" }},
      {{ key: "units_sold", label: "销量" }},
      {{ key: "total_viewers", label: "观看人数" }},
      {{ key: "live_count", label: "直播场次" }}
    ];
    const KPI_METRICS = [
      {{ key: "live_count", label: "直播场次" }},
      {{ key: "gmv", label: "GMV" }},
      {{ key: "units_sold", label: "销量" }},
      {{ key: "total_viewers", label: "观看人数" }}
    ];
    const COLORS = ["#2563eb", "#0f9f8f", "#e07a2f", "#d64550", "#6f5cc2", "#3a7d44", "#b15619"];
    let selectedMetric = "gmv";
    let selectedRegions = new Set();

    function n(value) {{
      const parsed = Number(value || 0);
      return Number.isFinite(parsed) ? parsed : 0;
    }}
    function fmt(value) {{
      const number = n(value);
      return new Intl.NumberFormat("zh-CN", {{ maximumFractionDigits: number >= 100 ? 0 : 2 }}).format(number);
    }}
    function escapeHtml(value) {{
      return String(value || "").replace(/[&<>"']/g, ch => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }}[ch]));
    }}
    function firstValue(row, keys) {{
      for (const key of keys) {{
        if (row[key] !== undefined && row[key] !== null && String(row[key]).trim() !== "") return row[key];
      }}
      return "";
    }}
    function regions() {{
      return [...new Set(ROOMS.map(row => row.region).filter(Boolean))].sort();
    }}
    function dates() {{
      return [...new Set(ROOMS.map(row => row.report_date).filter(Boolean))].sort();
    }}
    function activeRooms() {{
      if (!selectedRegions.size) return ROOMS;
      return ROOMS.filter(row => selectedRegions.has(row.region));
    }}
    function aggregateByDate(rows) {{
      const map = new Map();
      for (const row of rows) {{
        const day = row.report_date || "";
        if (!day) continue;
        if (!map.has(day)) map.set(day, {{ report_date: day, rooms: new Set(), gmv: 0, units_sold: 0, total_viewers: 0, live_count: 0 }});
        const bucket = map.get(day);
        bucket.rooms.add(row.room_key || row.room_id || `${{row.region}}-${{row.title}}-${{row.start_time}}`);
        bucket.gmv += n(row.gmv);
        bucket.units_sold += n(row.units_sold);
        bucket.total_viewers += n(row.total_viewers);
      }}
      return [...map.values()].map(row => ({{ ...row, live_count: row.rooms.size }})).sort((a, b) => a.report_date.localeCompare(b.report_date));
    }}
    function aggregateByRegion(rows, latestDate) {{
      const map = new Map();
      for (const row of rows.filter(item => item.report_date === latestDate)) {{
        const region = row.region || "UNKNOWN";
        if (!map.has(region)) map.set(region, {{ region, rooms: new Set(), gmv: 0, units_sold: 0, total_viewers: 0, live_count: 0 }});
        const bucket = map.get(region);
        bucket.rooms.add(row.room_key || row.room_id || `${{row.title}}-${{row.start_time}}`);
        bucket.gmv += n(row.gmv);
        bucket.units_sold += n(row.units_sold);
        bucket.total_viewers += n(row.total_viewers);
      }}
      return [...map.values()].map(row => ({{ ...row, live_count: row.rooms.size }})).sort((a, b) => n(b[selectedMetric]) - n(a[selectedMetric])).slice(0, 10);
    }}
    function renderControls() {{
      const metricBox = document.getElementById("metricButtons");
      metricBox.innerHTML = METRICS.map(metric => `<button type="button" data-metric="${{metric.key}}" class="${{metric.key === selectedMetric ? "active" : ""}}">${{metric.label}}</button>`).join("");
      metricBox.querySelectorAll("button").forEach(button => {{
        button.addEventListener("click", () => {{
          selectedMetric = button.dataset.metric;
          render();
        }});
      }});

      const regionBox = document.getElementById("regionFilter");
      const allRegions = regions();
      if (!selectedRegions.size) selectedRegions = new Set(allRegions);
      regionBox.innerHTML = allRegions.map(region => `<label><input type="checkbox" value="${{escapeHtml(region)}}" ${{selectedRegions.has(region) ? "checked" : ""}}>${{escapeHtml(region)}}</label>`).join("");
      regionBox.querySelectorAll("input").forEach(input => {{
        input.addEventListener("change", () => {{
          selectedRegions = new Set([...regionBox.querySelectorAll("input:checked")].map(item => item.value));
          render();
        }});
      }});
    }}
    function renderKpis(rows, latestDate) {{
      const latestRows = rows.filter(row => row.report_date === latestDate);
      const aggregate = aggregateByDate(latestRows)[0] || {{ live_count: 0, gmv: 0, units_sold: 0, total_viewers: 0 }};
      document.getElementById("kpis").innerHTML = KPI_METRICS.map(metric => `
        <article class="card kpi">
          <div class="label">${{metric.label}}</div>
          <div class="value">${{fmt(aggregate[metric.key])}}</div>
          <div class="sub">${{latestDate || "暂无日期"}}</div>
        </article>
      `).join("");
    }}
    function drawLine(canvas, points, metric) {{
      const ctx = canvas.getContext("2d");
      const width = canvas.width;
      const height = canvas.height;
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, width, height);
      if (!points.length) return drawEmpty(ctx, width, height);
      const pad = {{ left: 58, right: 18, top: 20, bottom: 42 }};
      const values = points.map(point => n(point[metric]));
      const max = Math.max(...values, 1);
      const min = 0;
      ctx.strokeStyle = "#d9e1ea";
      ctx.lineWidth = 1;
      ctx.fillStyle = "#697586";
      ctx.font = "12px system-ui";
      for (let i = 0; i <= 4; i++) {{
        const y = pad.top + (height - pad.top - pad.bottom) * i / 4;
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(width - pad.right, y);
        ctx.stroke();
        const label = fmt(max - (max - min) * i / 4);
        ctx.fillText(label, 8, y + 4);
      }}
      const xFor = index => pad.left + (width - pad.left - pad.right) * (points.length === 1 ? 0.5 : index / (points.length - 1));
      const yFor = value => height - pad.bottom - (height - pad.top - pad.bottom) * (n(value) - min) / (max - min || 1);
      ctx.strokeStyle = "#2563eb";
      ctx.lineWidth = 3;
      ctx.beginPath();
      points.forEach((point, index) => {{
        const x = xFor(index);
        const y = yFor(point[metric]);
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }});
      ctx.stroke();
      points.forEach((point, index) => {{
        const x = xFor(index);
        const y = yFor(point[metric]);
        ctx.fillStyle = index === points.length - 1 ? "#e07a2f" : "#2563eb";
        ctx.beginPath();
        ctx.arc(x, y, 4, 0, Math.PI * 2);
        ctx.fill();
      }});
      ctx.fillStyle = "#697586";
      const dateStep = Math.max(1, Math.ceil(points.length / 6));
      points.forEach((point, index) => {{
        if (index % dateStep && index !== points.length - 1) return;
        ctx.save();
        ctx.translate(xFor(index), height - 16);
        ctx.rotate(-0.2);
        ctx.fillText(point.report_date.slice(5), -16, 0);
        ctx.restore();
      }});
    }}
    function drawBars(canvas, rows, metric) {{
      const ctx = canvas.getContext("2d");
      const width = canvas.width;
      const height = canvas.height;
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, width, height);
      if (!rows.length) return drawEmpty(ctx, width, height);
      const pad = {{ left: 42, right: 14, top: 16, bottom: 38 }};
      const max = Math.max(...rows.map(row => n(row[metric])), 1);
      const barGap = 8;
      const barWidth = Math.max(16, (width - pad.left - pad.right - barGap * (rows.length - 1)) / rows.length);
      ctx.font = "12px system-ui";
      rows.forEach((row, index) => {{
        const value = n(row[metric]);
        const h = (height - pad.top - pad.bottom) * value / max;
        const x = pad.left + index * (barWidth + barGap);
        const y = height - pad.bottom - h;
        ctx.fillStyle = COLORS[index % COLORS.length];
        ctx.fillRect(x, y, barWidth, h);
        ctx.fillStyle = "#697586";
        ctx.fillText(row.region, x, height - 14);
      }});
    }}
    function drawEmpty(ctx, width, height) {{
      ctx.fillStyle = "#697586";
      ctx.font = "14px system-ui";
      ctx.textAlign = "center";
      ctx.fillText("暂无数据", width / 2, height / 2);
      ctx.textAlign = "left";
    }}
    function renderRooms(rows) {{
      const roomRows = rows
        .slice()
        .sort((a, b) => (b.report_date || "").localeCompare(a.report_date || "") || n(b.start_time) - n(a.start_time));
      document.getElementById("roomCount").textContent = `${{roomRows.length}} 场`;
      document.getElementById("roomRows").innerHTML = roomRows.map(row => `
        <tr>
          <td>${{escapeHtml(row.report_date)}}</td>
          <td>${{escapeHtml(row.region)}}</td>
          <td>${{escapeHtml(row.seller_name || row.seller_id)}}</td>
          <td>${{escapeHtml(row.creator_nickname || row.creator_unique_id)}}</td>
          <td class="title-cell" title="${{escapeHtml(row.title)}}">${{escapeHtml(row.title)}}</td>
          <td>${{escapeHtml(row.start_at)}}</td>
          <td>${{escapeHtml(row.currency)}}</td>
          <td>${{fmt(row.gmv)}}</td>
          <td>${{fmt(row.units_sold)}}</td>
          <td>${{fmt(row.total_viewers)}}</td>
          <td>${{fmt(row.max_concurrent_viewers)}}</td>
        </tr>
      `).join("");
    }}
    function renderTopSkus() {{
      const rows = TOP_SKUS.slice(0, 5);
      const hint = document.getElementById("skuHint");
      if (!rows.length) {{
        hint.textContent = "暂无 SKU 明细导出";
        document.getElementById("skuRows").innerHTML = `
          <tr>
            <td colspan="10">当前直播间导出只有场次级数据，无法计算 SKU 产品前五。请从 FastMoss 商品搜索/商品榜导出 SKU 明细后导入 data/top_skus.csv。</td>
          </tr>
        `;
        return;
      }}
      const updatedAt = firstValue(rows[0], ["updated_at", "导入时间", "更新时间"]);
      hint.textContent = updatedAt ? `SKU 数据更新时间：${{updatedAt}}` : `${{rows.length}} 个 SKU`;
      document.getElementById("skuRows").innerHTML = rows.map((row, index) => `
        <tr>
          <td class="rank">${{escapeHtml(firstValue(row, ["rank", "排名"]) || index + 1)}}</td>
          <td class="sku-product">${{escapeHtml(firstValue(row, ["product_name", "商品", "产品", "商品名称", "SKU", "sku_name"]))}}</td>
          <td>${{escapeHtml(firstValue(row, ["shop_name", "所属店铺", "店铺", "店铺名称"]))}}</td>
          <td>${{escapeHtml(firstValue(row, ["region", "国家", "地区", "区域"]))}}</td>
          <td>${{escapeHtml(firstValue(row, ["price", "price_range", "售价", "价格"]))}}</td>
          <td>${{escapeHtml(firstValue(row, ["seven_day_sales", "近7天销量"]))}}</td>
          <td>${{escapeHtml(firstValue(row, ["seven_day_gmv", "近7天销售额", "近7天GMV"]))}}</td>
          <td>${{escapeHtml(firstValue(row, ["total_sales", "总销量"]))}}</td>
          <td>${{escapeHtml(firstValue(row, ["total_gmv", "总销售额", "总GMV"]))}}</td>
          <td>${{escapeHtml(firstValue(row, ["source", "数据来源"]))}}</td>
        </tr>
      `).join("");
    }}
    function render() {{
      renderControls();
      const rows = activeRooms();
      const allDates = [...new Set(rows.map(row => row.report_date).filter(Boolean))].sort();
      const latestDate = allDates[allDates.length - 1] || "";
      document.getElementById("latestDate").textContent = latestDate ? `最新日期：${{latestDate}}` : "最新日期：-";
      if (!ROOMS.length) {{
        document.getElementById("kpis").innerHTML = "";
        document.getElementById("chartContent").innerHTML = '<div class="empty">暂无数据</div>';
        document.getElementById("roomRows").innerHTML = "";
        renderTopSkus();
        return;
      }}
      renderKpis(rows, latestDate);
      drawLine(document.getElementById("trendChart"), aggregateByDate(rows), selectedMetric);
      drawBars(document.getElementById("regionChart"), aggregateByRegion(rows, latestDate), selectedMetric);
      renderTopSkus();
      renderRooms(rows);
    }}
    render();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
