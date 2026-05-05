# ETF 资金流热力图设计文档

**日期：** 2026-05-05
**状态：** 已审批

---

## 目标

在 `/etf` 页面展示 75 只美股 ETF 的资金流强度热力图：
- 行：按 12 个中文板块分组，支持折叠/展开
- 列：最近 N 个交易日（默认 30），支持切换粒度（日/周/月）
- 颜色：红绿热力图，红色=资金流入，绿色=资金流出，深浅表示强度

---

## ETF 数据集

**75 只 ETF，12 个板块：**

| 编号 | 板块 | ETF 代码 |
|------|------|---------|
| 01 | 信息技术 | XLK, SOXX, AIQ, SKYY, QTUM, BUG, IGV |
| 02 | 医疗保健 | XLV, XHE, IHF, XBI, PJP |
| 03 | 金融 | XLF, KBE, IYG, KIE, BLOK, KCE, REM |
| 04 | 可选消费 | XLY, CARZ, XRT, XHB, PEJ |
| 05 | 必需消费 | XLP, PBJ, MOO |
| 06 | 工业 | XLI, ITA, PKB, PAVE, IYT, JETS, BOAT, IFRA, UFO, SHLD |
| 07 | 能源 | XLE, IEZ, XOP, FAN, TAN, NLR |
| 08 | 原材料 | XLB, PKB, XME, WOOD, COPX, GLD, GLTR, SLV, SLX, BATT |
| 09 | 通信服务 | XLC, IYZ, PNQI |
| 10 | 房地产 | XLRE, INDS, REZ, SRVR |
| 11 | 公用事业 | XLU, ICLN, PHO, GRID |
| 12 | 全球宏观/另类 | TLT, EEM, VEA, FXI, ARKK, BITO, MSOS, IPO, UFO, GBTC, ETHE |

---

## 计算公式

### 1. CLV（Close Location Value）
```
CLV = (2 × adjClose - adjHigh - adjLow) / (adjHigh - adjLow + 1e-9)
```
- 范围 [-1, 1]，衡量收盘价在当日区间的位置
- 分母加 1e-9 避免 adjHigh = adjLow 时除零

### 2. Flow（资金流强度原始值）
```
Flow = CLV × adjClose × volume
```

### 3. Intensity（标准化强度）
```
Intensity = (Flow - mean(所有ETF所有日期的Flow)) / (std(所有ETF所有日期的Flow) + 1e-9)
```
- **跨全样本** Z-score 标准化，保证跨 ETF 可比性
- std 为 0 时加 1e-9 避免除零

### 4. 粒度聚合
- **日**：直接使用每日 Intensity
- **周**：每自然周内的 Intensity 取均值，date_label 格式 `"2026-W18"`
- **月**：每自然月内的 Intensity 取均值，date_label 格式 `"2026-04"`

---

## 后端架构

### 新增/修改文件

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `app/services/etf/fetcher.py` | 替换 TRACKED_ETFS 为 75 只 ETF + 中文名，更新抓取字段为 adjOHLCV，添加 CLV/Flow 计算 |
| 修改 | `app/schemas/etf.py` | 新增 `HeatmapCell`、`HeatmapETFRow`、`HeatmapSectorGroup`、`HeatmapResponse` |
| 修改 | `app/cache/etf_cache.py` | 新增 `get_heatmap_cache` / `set_heatmap_cache` |
| 新增 | `app/api/v1/etf.py` | 单一端点 `GET /etf/heatmap` |
| 修改 | `app/api/v1/api.py` | 挂载 etf_router |

### API 端点

```
GET /api/v1/etf/heatmap?granularity=day&days=30
```

**参数：**
- `granularity`: `day` | `week` | `month`，默认 `day`
- `days`: 交易日数量，默认 30，最大 90

**响应体：**
```json
{
  "granularity": "day",
  "days": 30,
  "date_labels": ["2026-04-24", "2026-04-25", "..."],
  "sectors": [
    {
      "sector": "01 信息技术",
      "avg_cells": [
        {"date": "2026-04-24", "intensity": 0.42}
      ],
      "etfs": [
        {
          "symbol": "XLK",
          "name": "科技行业精选指数ETF-SPDR",
          "cells": [
            {"date": "2026-04-24", "intensity": 1.69}
          ]
        }
      ]
    }
  ]
}
```

**缓存：**
- key: `etf:heatmap:{granularity}:{days}`
- TTL: 3600s（FMP 免费版限额 250 次/天，75 只 ETF 一次请求后缓存）

### 错误处理
- 单只 ETF 请求失败 → 跳过，不影响其他 ETF
- adjHigh = adjLow → CLV = 0，Flow = 0
- 全样本标准差为 0 → Intensity 全为 0，前端显示中性色

---

## 前端架构

### 新增/修改文件

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `frontend/lib/api/etf.ts` | Axios 调用 + TypeScript 类型 |
| 新增 | `frontend/lib/store/etf.ts` | Zustand store（granularity + days 状态） |
| 新增 | `frontend/components/etf/GranularityToggle.tsx` | 日/周/月 切换按钮组 |
| 新增 | `frontend/components/etf/ETFHeatmapTable.tsx` | 主表格（折叠行、热力颜色、横向滚动） |
| 修改 | `frontend/app/(dashboard)/etf/page.tsx` | 替换骨架，组合以上组件 |

### 颜色规则

```typescript
// intensity > 0: 红色（资金流入）
// intensity < 0: 绿色（资金流出）
// 透明度 = min(|intensity| / 3, 1)

function intensityToColor(intensity: number): string {
  if (intensity === null) return 'bg-gray-50'
  const alpha = Math.min(Math.abs(intensity) / 3, 1)
  return intensity > 0
    ? `rgba(239, 68, 68, ${alpha})`   // red-500
    : `rgba(34, 197, 94, ${alpha})`   // green-500
}
```

### 表格布局
- 左侧**固定列**：板块/ETF 名称（200px）+ Ticker（80px）
- 右侧**横向滚动**：日期列（每列 72px）
- 板块行默认**折叠**，点击展开 ETF 明细
- 板块行显示该板块所有 ETF 的 **avg_cells**（板块平均强度）

### 交互状态
- 加载中：骨架屏（pulse 动画）
- 请求失败：错误提示 + 重试按钮
- 切换粒度：保留旧数据直到新数据返回（防闪烁）

---

## 范围外（本次不实现）

- ETF 搜索/过滤
- 点击行查看详情图表
- 数据自动刷新
- 移动端适配
