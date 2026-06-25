# A 股盘后复盘 Skill

这是一个面向 Codex / Agent Skills 的 A 股盘后复盘 Skill。

它不荐股，也不替用户做交易决策；它只处理用户指定的一只股票或一个小股票池。每次运行后，它会生成适合手机阅读的 HTML 复盘，并把当期判断保存成本地 JSON，方便下一次回看和校验。

## 适合什么场景

- 收盘后复盘一只 A 股，看今天发生了什么，原来的逻辑有没有变化
- 复盘一个小股票池，比较几只股票的当日表现、事件和后续观察条件
- 校验上一期判断，看当时列出的观察点今天有没有被验证
- 生成可归档、可转发的 HTML 盘后简报
- 用户提供持仓或交易记录时，顺带检查退出条件和纪律执行

## 核心能力

- 支持单只股票，也支持小股票池复盘。
- 校验上一期判断，并输出 `已验证 / 部分验证 / 未验证 / 已失效 / 无法判断`。
- 用本地 JSON 保存历史记录，默认放在 HTML 输出目录下的 `history/`。
- 引入市场、行业和产业链背景作对照，用来区分市场、行业、上下游和个股因素。
- 按触发规则处理公告、业绩、会议、政策、行业和上下游新闻。
- 将"能否判断"和"方向倾向"分开处理。证据充分时输出 `向上 / 维持震荡 / 向下`；证据不足时明确标注，不把缺数据硬写成震荡。
- 基于日 K 的本地特征计算，覆盖收益率、均线、趋势结构、收盘位置、量能状态、区间突破、波动、缺口和相对表现。
- 将个股自身技术结构与大盘、行业相对表现分开呈现，避免相对跑赢或跑输掩盖价格和量能本身的状态。
- 基于两只股票的 K 线收益率计算 Pearson 相关性。
- 使用适合手机阅读和邮件附件的现代扁平风 HTML 模板，A 股方向标签遵循红涨绿跌。
- 用户需要时，可以生成简短 Gmail 草稿正文。HTML 附件是否已添加，需要以 Gmail 工具返回结果为准。
- 只有在用户提供持仓、交易记录或明确要求时，才做持仓纪律检查。

## 能力边界

- 不默认给出买入或卖出建议
- 不执行交易
- 不给确定性价格预测或目标价
- K 线特征只是复盘证据，不是独立预测或交易信号
- 不做完整全市场复盘
- 不默认生成周报或长期记忆

## 安装

### 使用 npm / npx

```bash
npx a-share-after-hours-brief-skill install
```

默认安装位置：

```text
~/.codex/skills/a-share-after-hours-brief/
```

覆盖已有安装：

```bash
npx a-share-after-hours-brief-skill install --force
```

`--force` 会先把已有安装移动到带时间戳的备份目录。只有在明确不需要备份时，才使用 `--force --no-backup`。

安装到自定义 skills 目录：

```bash
npx a-share-after-hours-brief-skill install --target /path/to/skills
```

### 从 GitHub 安装

如果 npm 暂时不可用，可以直接从 GitHub 安装：

```bash
npx github:SkyBridgeM/a-share-after-hours-brief-skill install
```

### 手动安装

在仓库根目录下，把 Skill 文件复制到 Codex 约定的安装目录：

```bash
mkdir -p ~/.codex/skills/a-share-after-hours-brief
cp -R SKILL.md agents assets config references scripts schemas examples \
  ~/.codex/skills/a-share-after-hours-brief/
```

## 使用示例

```text
复盘今天的宁德时代
```

```text
今天 A 股股票 A 和股票 B 盘后总结，输出 HTML
```

```text
校验上次判断，列出下一交易日验证条件
```

```text
复盘这几只 A 股，并创建 Gmail 草稿
```

## 输出内容

生成的 HTML 复盘通常包括：

1. 今日结论
2. 精简市场背景
3. 上一期判断验证
4. 股票池概览
5. 个股复盘卡片
6. 重大事项
7. 行业与产业链新闻
8. 相关性
9. 下一交易日评估和验证条件
10. 可选持仓纪律检查

下一交易日部分会先判断证据是否足够。证据充分时，在 `向上 / 维持震荡 / 向下` 中选择一档，并标注信心等级；证据不足时会明确写出，不强行给出震荡判断。它不是交易指令，也不提供目标价。

K 线输出分为两层：一层是个股自身的技术结构，另一层是相对大盘或行业的表现。数据质量限制会按特征组呈现，尤其是量能数据或对比数据不完整时。

## 历史 JSON

历史记录默认保存在 HTML 输出目录旁：

```text
reports/
├── 2026-06-16__a-share-after-hours__300750-SZ_600519-SH.html
└── history/
    └── 2026-06-16__300750-SZ_600519-SH.json
```

历史记录规则：

- JSON 是唯一结构化历史数据源
- 不生成 Markdown 历史日志
- 不保存绝对路径
- `generated_at` 使用带时区偏移的 ISO 8601 时间；A 股报告默认使用 Asia/Shanghai
- 整个报告目录可以直接移动或备份
- 同一天重复运行同一个股票池时，会更新对应 JSON
- 损坏或不兼容的历史文件会以结构化 warning 呈现，不会静默跳过
- 正式 schema 位于 `schemas/history-v1.schema.json`，示例记录位于 `examples/history-record.example.json`

## 文件命名

新的本地文件统一使用稳定的 ASCII 文件名，中文标题保留在 HTML 或 Markdown 内容里。目录名可以配置；这里标准化的是文件命名，不是强制固定唯一存储路径。

| 文件类型 | 命名格式 |
| --- | --- |
| HTML 报告 | `<report-output-dir>/YYYY-MM-DD__a-share-after-hours__<sorted-stock-codes>.html` |
| history JSON | `<history-dir>/YYYY-MM-DD__<sorted-stock-codes>.json` |
| 运行状态 / 日志 | `<state-or-log-dir>/YYYY-MM-DD.<purpose>.json`、`.txt` 或 `.log` |
| 原始运行数据 | `<data-dir>/YYYY-MM-DD-data/<code>_<kind>.json`，或其他带日期的 `data` / `raw_data` 路径 |
| 月度总结 | `monthly-summary-YYYY-MM.html`、`.md` 或 `.json` |

示例文件名：`2026-06-25__a-share-after-hours__002745-SZ_301307-SZ.html`。

## 本地存储清理

报告目录用久了以后，HTML、原始数据、日志和缓存会慢慢堆起来。这个 Skill 提供了一个本地清理脚本，默认只预览，不会直接删除文件；只有显式加上 `--apply`，才会真正清理。

默认保留策略：

| 类型 | 保留时间 |
| --- | ---: |
| HTML 报告 | 30 天 |
| 图表 | 30 天 |
| 原始数据 | 14 天 |
| 缓存 | 7 天 |
| 日志 | 14 天 |
| history JSON | 90 天 |
| 月度总结 | 长期保留 |

先预览：

```bash
python3 scripts/cleanup_reports.py --root ./reports
```

如果旧项目把产物分散放在多个地方，例如 HTML 报告在工作区根目录、`history/` 也在根目录，或另有原始数据、运行状态、日志目录，可以对工作区根目录做预览：

```bash
python3 scripts/cleanup_reports.py --root .
```

确认无误后再删除：

```bash
python3 scripts/cleanup_reports.py \
  --root ./reports \
  --policy config/storage-policy.example.json \
  --apply
```

脚本会列出准备删除的文件、预计释放的空间，以及跳过某些文件的原因。当前月份的文件不会删除。超过 90 天的 history JSON 也不会立刻删，只有同月份的月度总结已经存在时，脚本才允许清理对应的日度历史记录。`logs/`、`state/`、`run-state/`、`runtime/`、`automation-state/` 等明显运行状态或日志目录下的带日期 JSON/TXT/LOG 文件按日志处理。带日期的 `data`、`raw_data` 或 `*-data` 产物按原始数据处理。普通业务 JSON 默认不会因为扩展名是 `.json` 而被清理。

## 仓库结构

```text
.
├── SKILL.md
├── agents/
│   └── openai.yaml
├── assets/
│   ├── brief-template.html
│   └── plain-email-summary-template.md
├── config/
│   └── storage-policy.example.json
├── examples/
│   └── history-record.example.json
├── references/
│   ├── data-providers.md
│   ├── event-triggers.md
│   ├── history-and-review.md
│   ├── html-email.md
│   ├── industry-news.md
│   ├── kline-analysis.md
│   └── wind-data.md
├── schemas/
│   └── history-v1.schema.json
└── scripts/
    ├── cleanup_reports.py
    ├── correlation.py
    ├── kline_features.py
    └── review_journal.py
```

## 脚本说明

计算本地 K 线结构特征：

```bash
python3 scripts/kline_features.py stock.json
```

带基准和行业相对强弱的 K 线特征：

```bash
python3 scripts/kline_features.py stock.json \
  --benchmark benchmark.json \
  --sector sector.json \
  --adjustment forward
```

计算两只股票收益率相关性：

```bash
python3 scripts/correlation.py stock_a.json stock_b.json
```

查找上一期历史记录：

```bash
python3 scripts/review_journal.py lookup \
  --history-dir ./reports/history \
  --before-date 2026-06-16 \
  --stocks 300750.SZ,600519.SH
```

生成并保存当前历史记录：

```bash
python3 scripts/review_journal.py build \
  --input current-draft.json \
  --output-html ./reports/2026-06-16_A股盘后复盘.html
```

预览本地存储清理：

```bash
python3 scripts/cleanup_reports.py --root ./reports
```

确认 dry-run 输出后，再执行删除：

```bash
python3 scripts/cleanup_reports.py --root ./reports --apply
```

## 依赖

- Python 3.10+
- Node.js 18+，仅用于 npm 安装脚本
- Codex / Agent Skills 兼容客户端
- A 股行情、复权 K 线、公告、财务事实、基准指数和新闻等金融数据能力；可用时优先使用 Wind MCP
- [Agent Reach](https://github.com/Panniantong/Agent-Reach) 可选，用于补充外部网页、行业协会、上下游和同业新闻搜索
- Gmail 连接器，仅在需要创建 Gmail 草稿时使用

内置 Python 脚本只使用标准库。

## 本地校验

```bash
npm run check
```

也可以单独检查 Python 脚本：

```bash
PYTHONPYCACHEPREFIX=/tmp/a-share-after-hours-brief-skill-pycache \
python3 -m py_compile scripts/review_journal.py scripts/correlation.py scripts/kline_features.py scripts/cleanup_reports.py
```

完整 `npm run check` 还会运行 Python 单元测试和 Node.js 安装器测试，测试依赖只使用标准库和 Node.js 内置模块。

如果你有 Skill Creator 的验证脚本：

```bash
python3 /path/to/skill-creator/scripts/quick_validate.py ./a-share-after-hours-brief
```

## 数据和隐私

生成的 HTML 报告、`history/*.json`、原始数据、缓存、持仓记录和交易记录都保存在用户本地输出目录。这个 Skill 不会上传这些文件，也不会集中存储用户数据。需要整理旧文件时，先用 `scripts/cleanup_reports.py` 预览，再决定是否删除。

本仓库只包含可复用的 Skill 逻辑、模板和说明，不内置 Wind、Gmail 或其他 API 凭证。

## 发布

包名：

```text
a-share-after-hours-brief-skill
```

安装命令：

```bash
npx a-share-after-hours-brief-skill install
```

GitHub 仓库：

```text
https://github.com/SkyBridgeM/a-share-after-hours-brief-skill
```

## 免责声明

本 Skill 仅用于研究记录和工作流自动化，不构成投资建议、交易指令或收益承诺。投资决策由用户自行承担。

## License

MIT License. See [LICENSE](LICENSE).
