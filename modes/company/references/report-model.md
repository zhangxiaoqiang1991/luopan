# 统一报告模型

## 何时读取

完成事实搜集和判断后、生成 JSON、HTML 或 Markdown 前读取。

## 真源原则

JSON 是可追溯的事实与报告底稿。HTML 和 Markdown 必须由同一份 JSON 通过 `scripts/render_report.py` 生成，不得分别即兴改写。

V1 顶层字段：

```json
{
  "company": {},
  "research_date": "2026-07-12",
  "presentation": {
    "primary_audience": "investment",
    "secondary_policy": "collapsed",
    "reason": "用户选择：投资为主"
  },
  "summary": {},
  "data_health": [],
  "facts": [],
  "sections": [],
  "sources": [],
  "interview_questions": [],
  "quiz_cards": []
}
```

`company`、`research_date`、`summary`、`sections`、`sources` 和 `quiz_cards` 为必需；`data_health` 和 `facts` 为可选，但深度报告应当生成。
求职主视角、双主线或用户明确要求求职判断的报告必须包含 10 条 `interview_questions`。投资主视角的默认报告可以只保留折叠的公司级求职入口，待用户追问具体求职研究后再生成10问。字段至少包含 `id`、`dimension`、`question`、`why`、`follow_up`、`ask_to`、`green`、`yellow`、`red`，并可用 `priority: true` 标记 3 个优先问。`question` 与 `follow_up` 必须采用低防御话术；红黄绿只用于用户后台复盘。

## `company` 与 `summary`

`company` 至少记录 `name` 和上市状态，并可增加上市地、代码、母子公司关系和唯一实体 ID。`summary` 至少包含 `headline`，并按任务填写 `investment` 和 `career`。

## `facts`

每条事实至少使用渲染器可校验的字段：

```json
{
  "id": "fact_revenue_fy2025",
  "field": "营收",
  "value": 1000000000,
  "period": "FY2025",
  "source_ids": ["src_10k_2025"],
  "confidence": "high",
  "is_calculated": false,
  "is_inference": false
}
```

按可得性增加 `currency`、`unit`、`scope`、期间起止、页码/章节、获取时间和冲突关系。计算值必须设置 `is_calculated: true` 并提供 `calculation`；推断必须设置 `is_inference: true`，不得伪装成原始事实。`source_ids` 必须指向 `sources` 中已存在的 ID。

## `data_health`

数据健康度是按维度记录的数组，不压成单一总分：

```json
{
  "dimension": "财务",
  "status": "partial",
  "obtained": 6,
  "required": 8,
  "notes": "缺少可比的分部现金流"
}
```

`status` 只使用 `complete`、`partial`、`missing`、`conflict`、`stale` 或 `not_applicable`。`not_applicable` 不计入缺失；不要为提高完整度而引用低质量数据。

这些英文值只用于 JSON 与样式类名。HTML 和 Markdown 必须显示对应中文：`完整`、`部分完整`、`缺失`、`存在冲突`、`已过期`、`不适用`。

## `sections`

V1 呈现章节使用：

```json
{
  "title": "财务质量",
  "audience": "investment",
  "body": "利润与经营现金流大体同步……",
  "evidence_ids": ["src_10k_2025"]
}
```

`sections` 是呈现层，不替代 `facts`。核心数字和判断必须能回指事实或来源。
`audience` 可取 `investment`、`career` 或 `shared`；当 `presentation.secondary_policy` 为 `collapsed` 时，次视角章节默认折叠。

## `sources`

```json
{
  "id": "src_10k_2025",
  "title": "2025 财年 Form 10-K 年报",
  "original_title": "FY2025 Form 10-K",
  "language": "en",
  "url": "https://...",
  "level": "A级"
}
```

`url` 是实际读取的可点击页面。需要同时保留二手页面与原始材料时，建立两条来源记录并明确分级，不把二手页面冒充原始证据。
`title` 为面向用户的中文标题；外文来源应增加 `original_title` 和 `language`，中文官方来源可省略 `original_title`。具体规则见 [language-and-sources.md](language-and-sources.md)。

## `quiz_cards`

每张卡片遵守 [quiz-cards.md](quiz-cards.md)，必须是 `single_choice` 或 `multiple_choice`，并包含 `correct_option_ids`、`option_explanations`、`related_sections`、`evidence_ids` 和 `follow_up_prompt`。正确答案必须能回指报告事实或来源。

## 渲染契约

1. 先写完整 JSON，再运行 `python3 scripts/render_report.py <input.json> --output-dir <dir>`。
2. 渲染器会校验核心字段、事实来源、计算说明和选择题答案。
3. 不在渲染后手工改写 HTML 或 Markdown；需修改时回到 JSON 真源。
4. 渲染后检查公司名、研究日期、核心判断、来源数和选择题答案是否一致。
