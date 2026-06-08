# FastMoss Manual Exports

如果 Chrome 扩展无法安装，可以先从 FastMoss 网页手动导出 POP MART 官方店铺直播间明细 CSV，然后放到这个目录。

推荐文件名：

```text
popmart-live-YYYY-MM-DD.csv
```

导入并重建网页：

```bash
python3 scripts/import_fastmoss_export.py imports/popmart-live-YYYY-MM-DD.csv --date YYYY-MM-DD --render
```

脚本会自动识别常见中文和英文列名，例如：

- 日期 / Date / report_date
- 国家 / 地区 / region / country
- 直播间ID / room_id / live_id
- 店铺 / shop / seller_name
- 达人 / creator / nickname
- 直播标题 / title
- 开始时间 / start_time
- GMV / 成交金额 / 销售额
- 销量 / units_sold
- 观看人数 / viewers
- 峰值在线 / max_concurrent_viewers

如果 CSV 没有日期列，需要使用 `--date` 指定统计日期。

## POP MART 官方店铺口径

直播间导入和日度更新默认只保留官方店铺，不保留标题或达人昵称里碰巧包含 POP MART 的第三方店铺。品牌文本会识别以下写法：

- `POP MART`
- `popmart`
- `pop mart`

如果确实要临时保留第三方店铺，可额外传 `--include-third-party`；日常看板不要使用这个参数。

## SKU 前五导入

现有直播间导出是场次级数据，只包含每场直播的销量、GMV、观看、商品数，不包含 SKU/产品明细。要在网页里显示“销售前五 SKU 产品”，需要从 FastMoss 商品搜索、商品榜或直播商品明细导出 SKU 级 CSV，再导入：

```bash
python3 scripts/import_fastmoss_sku_export.py imports/popmart-sku-YYYY-MM-DD.csv --period-start YYYY-MM-DD --period-end YYYY-MM-DD --render
```

脚本会按 `popmart`、`pop mart`、`POP MART` 过滤商品名，并要求店铺命中官方店铺别名，默认按近 7 天销量排序，保留前五到 `data/top_skus.csv`。
