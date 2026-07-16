# 骑手装备商城 · 社交媒体内容营销自动化产品

## 1. 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      内容营销中台                              │
├──────────────┬──────────────┬──────────────┬──────────────┤
│  热点采集层   │  内容生成层   │  输出交付层   │  调度执行层   │
├──────────────┼──────────────┼──────────────┼──────────────┤
│ 抖音热点榜    │ AI 选题生成   │ 活动策划案    │ 每日定时任务  │
│ 小红书热搜    │ 脚本/文案生成  │ 内容排期表    │ 自动化推送   │
│ 电商行业趋势  │ 关键词标签生成 │ 达人brief    │ 异常告警     │
│ 竞品动态     │ 视觉风格建议   │ 数据追踪表    │ 手动触发     │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

## 2. 核心流程

1. **每日 09:00** → 自动采集各平台热点数据
2. **09:30** → AI 结合品牌/产品/营销日历，生成热点关联内容选题
3. **10:00** → 输出：活动策划案 + 内容脚本 + 排期表 + 达人 brief
4. **输出到** → `M:\营销工作\每日热点内容输出\`（按日期归档）

## 3. 平台覆盖

| 平台 | 采集内容 | 输出形式 |
|------|---------|---------|
| 抖音 | 热点榜、挑战榜、热门话题 | 短视频脚本、话题参与策略 |
| 小红书 | 热搜词、爆款笔记、热门话题 | 种草文案、图文笔记脚本、达人 brief |
| 电商站内 | 品类趋势、搜索热词、竞品活动 | 促销活动方案、站内内容排期、资源位素材建议 |

## 4. 技术栈

- **Python 3.11+**：数据采集、处理、AI 调用
- **Playwright / CatDesk Browser**：网页热点采集（不依赖 API 权限）
- **OpenAI / 通义千问**：内容生成（通过 OpenRouter 或国内 API）
- **Pandas + OpenPyXL**：数据处理与 Excel 输出
- **python-docx**：Word 报告输出
- **Windows 计划任务 / CatPaw Automation**：每日定时执行

## 5. 项目目录

```
M:\social-media-marketing-auto/
├── config/
│   ├── settings.yaml          # 全局配置（API Key、平台开关、输出路径）
│   ├── marketing_calendar.yaml # 营销日历（大促节点、品类日）
│   └── brand_keywords.yaml      # 品牌/产品关键词库
├── collectors/
│   ├── base.py                # 采集器基类
│   ├── douyin_hot.py          # 抖音热点采集
│   ├── xiaohongshu_hot.py     # 小红书热搜采集
│   ├── ecommerce_trend.py     # 电商趋势采集
│   └── competitor_monitor.py  # 竞品监控
├── generators/
│   ├── base.py                # 生成器基类
│   ├── topic_selector.py      # 选题匹配（热点 × 产品 × 营销日历）
│   ├── content_writer.py      # 内容文案生成
│   ├── script_generator.py    # 短视频脚本生成
│   └── brief_generator.py     # 达人 brief 生成
├── outputs/
│   ├── excel_reporter.py      # Excel 排期表输出
│   ├── word_reporter.py       # Word 活动策划案输出
│   └── markdown_reporter.py # Markdown 速览报告
├── scheduler/
│   └── daily_task.py          # 每日定时任务编排
├── utils/
│   ├── ai_client.py           # AI API 统一封装
│   ├── file_manager.py        # 文件归档管理
│   └── logger.py              # 日志
├── data/                       # 历史数据存储
│   └── hot_data/              # 每日热点原始数据
├── outputs_daily/              # 每日输出目录
└── main.py                     # 主入口
```

## 6. 运行方式

```bash
# 手动执行今日热点内容生成
python main.py --date today

# 生成指定日期内容（补跑）
python main.py --date 2025-07-15

# 仅采集热点（不生成内容）
python main.py --mode collect

# 仅生成内容（基于已采集热点）
python main.py --mode generate
```
