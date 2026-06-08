# POP MART FastMoss Global Live Tracker

这个仓库用于在 FastMoss 平台上日度抓取 POP MART 全球直播间数据，沉淀 CSV/JSON，并生成一个可发布到 GitHub Pages 的静态趋势网页。

## 当前状态

- 数据源：FastMoss OpenAPI
- 目标：所有 POP MART 官方店铺直播间，不包含第三方店铺/达人账号
- 默认统计日：Asia/Shanghai 自然日的昨天
- 公网入口：[FastMoss POP MART Dashboard](https://unclejeremy728.github.io/jeremy/fastmoss-popmart/)
- 本地入口：[docs/index.html](/Users/jeremy/Documents/fastmoss数据追踪/docs/index.html)

FastMoss 官方 OpenAPI 文档入口：

- [Quick Start](https://developers.fastmoss.com/docs/guide/quickStart.html)
- [Live Search](https://developers.fastmoss.com/docs/live/v1/search.html)
- [Shop Search](https://developers.fastmoss.com/docs/shop/v1/search.html)
- [Shop Related Live Stream List](https://developers.fastmoss.com/docs/shop/v1/liveList.html)

## 配置 FastMoss 授权

在仓库根目录创建 `.env`：

```bash
FASTMOSS_CLIENT_SECRET=your_client_secret_here
```

也可以在命令前临时注入：

```bash
FASTMOSS_CLIENT_SECRET=your_client_secret_here python3 scripts/update_popmart_daily.py --render
```

脚本只读取 OpenAPI `client_secret`，不会读取浏览器 cookies、密码或本地存储。

## 手动更新

抓取昨天数据并重建网页：

```bash
python3 scripts/update_popmart_daily.py --render
```

抓取指定日期：

```bash
python3 scripts/update_popmart_daily.py --date 2026-06-07 --render
```

只重建网页：

```bash
python3 scripts/build_dashboard.py
```

## Chrome 扩展无法安装时

不影响整体方案。可以先从 FastMoss 网页手动导出 POP MART 直播间明细 CSV，放到 `imports/`，然后导入。导入时默认只保留官方店铺：

```bash
python3 scripts/import_fastmoss_export.py imports/popmart-live-2026-06-07.csv --date 2026-06-07 --render
```

如果 CSV 里已有日期列，可以不传 `--date`。如果导出内容不止 POP MART，可以加 `--filter-popmart` 先做品牌文本过滤；最终仍会按官方店铺口径清洗：

```bash
python3 scripts/import_fastmoss_export.py imports/export.csv --date 2026-06-07 --filter-popmart --render
```

这个入口会和 OpenAPI 日更共用同一份 `data/live_rooms.csv`、`data/daily_summary.csv` 和 `docs/index.html`。

输出文件：

- `data/live_rooms.csv`：直播间明细
- `data/daily_summary.csv`：日度聚合
- `data/top_skus.csv`：SKU 销售前五，来自 FastMoss 商品/SKU 明细导出
- `data/raw/YYYY-MM-DD.json`：当日原始抓取快照
- `docs/index.html`：静态趋势页

## SKU 销售前五

直播间导出是场次级数据，不包含具体 SKU/产品名。网页已经预留“销售前五 SKU 产品”模块；从 FastMoss 商品搜索、商品榜或直播商品明细导出 SKU 级 CSV 后，运行：

```bash
python3 scripts/import_fastmoss_sku_export.py imports/popmart-sku-YYYY-MM-DD.csv --period-start YYYY-MM-DD --period-end YYYY-MM-DD --render
```

脚本会按 `POP MART`、`popmart`、`pop mart` 过滤商品名，并要求店铺命中官方店铺别名，默认按近 7 天销量排序，保留前五到 `data/top_skus.csv` 并重建网页。

## 日度自动更新

`.github/workflows/daily-popmart-fastmoss.yml` 已配置 GitHub Actions：

- 每天北京时间 09:20 运行
- 需要在 GitHub 仓库 Secret 中配置 `FASTMOSS_CLIENT_SECRET`
- 自动提交更新后的 `data/` 和 `docs/index.html`

公网版本已发布到 `unclejeremy728/jeremy` 仓库的 `fastmoss-popmart/` 目录。线上 workflow 每天更新源数据后，会把最新静态页同步到 `gh-pages` 分支，因此固定链接为：

```text
https://unclejeremy728.github.io/jeremy/fastmoss-popmart/
```

## POP MART 店铺识别

默认配置在 [config/popmart_fastmoss.json](/Users/jeremy/Documents/fastmoss数据追踪/config/popmart_fastmoss.json)。脚本会：

1. 按区域和官方账号别名搜索 POP MART 官方店铺；
2. 只保留命中 `official_shop_aliases` 或官方地区/账号标记的店铺；
3. 拉取这些官方店铺关联的直播间，并用直播搜索补充遗漏场次；
4. 导入、抓取、汇总时都会剔除第三方店铺/达人账号；
5. 按 `room_id` 去重并累计。

当前官方别名已补充新加坡、泰国、越南、菲律宾/马来西亚、英国等官方 TikTok Shop 入口。如果 FastMoss 搜索仍漏掉某些官方店铺，可以在 `manual_shops` 中补充 `seller_id`，然后把 `enabled` 设为 `true`。
