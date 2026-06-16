# A Share After-Hours Brief Skill

面向 Codex / Agent Skills 的 **A 股个股盘后复盘 Skill**。

它不是荐股工具，也不是全市场复盘工具。它聚焦用户指定的一只或多只 A 股，生成移动端友好的 HTML 盘后复盘，并用本地 JSON 记录上一期判断，方便下次自动校验。

## 适合什么场景

- 收盘后复盘一只 A 股：今天发生了什么，逻辑有没有变化
- 复盘一个小股票池：比较几只股票当日表现、事件和后续观察条件
- 校验上一次判断：上一期说要观察什么，今天是否被验证
- 生成可归档、可转发的 HTML 盘后简报
- 在提供持仓或交易记录时，顺带检查退出条件和纪律执行

## 核心能力

- **个股 / 股票池盘后复盘**：支持一只或多只 A 股。
- **上一期判断校验**：输出 `已验证 / 部分验证 / 未验证 / 已失效 / 无法判断`。
- **本地 JSON 历史记录**：默认保存到 HTML 输出目录下的 `history/`。
- **市场和行业背景**：只作对照，用于区分市场、行业和个股因素。
- **重大事项和行业新闻**：按触发规则处理公告、业绩、会议、政策和行业变化。
- **相关性计算**：基于两只股票 K 线收益率计算 Pearson 相关性。
- **移动端 HTML 模板**：适合手机阅读和邮件附件。
- **Gmail 草稿模板**：可生成简短邮件正文，并附 HTML 报告。
- **持仓纪律检查**：仅在用户提供持仓、交易记录或明确要求时启用。

## 不做什么

- 不提供默认买卖建议
- 不执行交易
- 不预测 1-3 日价格走势
- 不做完整全市场复盘
- 不默认生成周报或长期记忆
- 不上传或集中存储用户历史记录
- 不内置 Wind、Gmail 或任何 API 凭证

## 安装

### 使用 npm / npx

```bash
npx a-share-after-hours-brief-skill install
```

默认安装到：

```text
~/.codex/skills/a-share-after-hours-brief/
```

覆盖已有安装：

```bash
npx a-share-after-hours-brief-skill install --force
```

安装到自定义 skills 目录：

```bash
npx a-share-after-hours-brief-skill install --target /path/to/skills
```

### 从 GitHub 安装

如果 npm 暂时不可用，也可以直接从 GitHub 安装：

```bash
npx github:SkyBridgeM/a-share-after-hours-brief-skill install
```

### 手动安装

复制整个目录到 Codex skills 目录：

```bash
cp -R a-share-after-hours-brief ~/.codex/skills/
```

## 使用示例

```text
复盘今天的宁德时代
```

```text
今天A股股票A和股票B盘后总结，输出HTML
```

```text
校验上次判断，列出下一交易日验证条件
```

```text
复盘这几只A股，并创建Gmail草稿
```

## 输出内容

生成的 HTML 复盘通常包括：

1. 今日结论
2. 精简市场背景
3. 上一期判断验证
4. 股票池概览
5. 个股复盘卡片
6. 重大事项
7. 行业新闻
8. 相关性
9. 下一交易日重点观察
10. 可选持仓纪律检查

其中“下一交易日重点观察”只列可验证条件，不给确定方向或价格预测。

## 历史 JSON

历史记录默认保存在 HTML 输出目录旁：

```text
reports/
├── 2026-06-16_A股盘后复盘.html
└── history/
    └── 2026-06-16__300750-SZ_600519-SH.json
```

设计原则：

- JSON 是唯一结构化历史数据源
- 不生成 Markdown 历史日志
- 不保存绝对路径
- 整个报告目录可以直接移动或备份
- 同日同股票池重复运行时，会更新对应 JSON

## 目录结构

```text
a-share-after-hours-brief/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── assets/
│   ├── brief-template.html
│   └── plain-email-summary-template.md
├── references/
│   ├── event-triggers.md
│   ├── history-and-review.md
│   ├── html-email.md
│   ├── industry-news.md
│   └── wind-data.md
└── scripts/
    ├── correlation.py
    └── review_journal.py
```

## 脚本说明

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

## 依赖

- Python 3.10+
- Node.js 18+，仅用于 npm 安装脚本
- Codex / Agent Skills 兼容客户端
- Wind 数据能力，用于 A 股行情、K 线、公告和新闻
- Gmail 连接器，仅在需要创建 Gmail 草稿时使用

内置 Python 脚本只使用标准库。

## 本地校验

```bash
npm run check
```

也可以单独检查 Python 脚本：

```bash
PYTHONPYCACHEPREFIX=/tmp/a-share-after-hours-brief-skill-pycache \
python3 -m py_compile scripts/review_journal.py scripts/correlation.py
```

如果你有 Skill Creator 的验证脚本：

```bash
python3 /path/to/skill-creator/scripts/quick_validate.py ./a-share-after-hours-brief
```

## 数据和隐私

不要提交生成的 HTML 报告、`history/*.json`、持仓记录或交易记录。本仓库只发布可复用的 Skill 逻辑、模板和说明文件。

`.gitignore` 已默认排除常见输出目录和历史数据。

## 发布

当前包名：

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

本 Skill 仅用于研究记录和工作流自动化，不构成投资建议、交易指令或收益承诺。所有投资决策由用户自行承担。

## License

MIT License. See [LICENSE](LICENSE).
