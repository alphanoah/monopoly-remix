# tools · 构建链说明

仓库里所有「手写 md/json 真源 → 页面」的转换都在这里。入口是 `build.py`：

```bash
python3 tools/build.py                    # 全部跑一遍（等价于双击 update.command）
python3 tools/build.py --step gen_pages   # 只跑某一步，可逗号多个
```

push 后 GitHub Actions（`.github/workflows/build-pages.yml`）跑的是同一个脚本。

## 文件清单

| 文件 | 作用 |
|---|---|
| `build.py` | 入口。顶部是声明式配置：RULE_DOCS（多版规则）、ORIGINAL_DOCS、PAGES（站点地图）、STEPS（步骤链） |
| `import-cards.py` | 卡牌 CSV → `source/cards.md` 回导（配合首页「导出 CSV / Excel」批量编辑；校验 + 回读比对，不一致不写） |
| `steps/validate.py` | 校验真源：卡牌硬失败（不写任何文件），棋盘/道具软失败（跳过相关块） |
| `steps/gen_data.py` | 生成 `data/cards.json`、`data/props.json` |
| `steps/gen_pages.py` | 重写 `index.html` / `original.html` / `print.html` 的标记块 |
| `steps/gen_map.py` | 回写 `map.html` 的地图兜底数据 |
| `steps/gen_docs.py` | 把 `docs/` 下的文档转成 `other/` 独立页面 + 索引页（见下） |
| `steps/gen_readme.py` | 刷新 `README.md` 的「数据速览」块 |
| `lib/md.py` | 简易 md → HTML（标题/列表/引用/表格/链接/粗体/行内码） |
| `lib/cards.py` | cards.md 三层结构（版本→花色→表格）的解析 / 校验 / 生成 |
| `lib/mapdata.py` | `source/map-print-data.json` 的解析与统计表生成 |
| `lib/props.py` | `source/props.md` 道具清单解析 |
| `lib/html_block.py` | 标记块替换（`<!-- XXX:START -->...<!-- XXX:END -->`），手改部分不动 |
| `lib/ctx.py` | 步骤间共享的真源缓存（按需加载） |
| `lib/paths.py` | 全部路径常量 |

## 真源 → 产物链路

| 真源（手写） | 产物（脚本生成，勿手改） |
|---|---|
| `source/cards.md` | `data/cards.json` + `index.html` 卡牌区 + `print.html` 兜底 |
| `source/new-rule-v3.md`（v3，现行）| `index.html` 规则 tab（默认打开） |
| `source/new-rule.md`（v2，过渡）| `index.html` 规则 tab |
| `source/rules.md`（v1，朋友初版）| `index.html` 规则 tab |
| `source/original/manual.md` | `index.html` 原版 tab + `original.html` |
| `source/original/cards.md` | `original.html` |
| `source/original/map-data-guide.md` | `original.html` 折叠区块（统计表由脚本现算插入） |
| `source/original/map-tiles.md` | `original.html` 折叠区块（同上） |
| `source/props.md` | `index.html` 道具区 + `data/props.json` + `print.html` 兜底 |
| `source/map-print-data.json` | `map.html` 兜底 + `index.html` 地图区 + README 速览 |
| `docs/*.md`（build.py 的 DOCS 登记的 4 篇） | `other/<同名>.html` + `other/index.html` 索引页 |

产物页面里只有 `<!-- XXX:START/END -->` 标记块内的内容会被脚本覆盖，块外的手写部分（页面骨架、样式、交互 JS）不受影响。

## 仓库 md 统计

**已入构建链（9 个）**：上表左侧全部。它们不是独立页面，而是注入
`index.html` / `original.html` / `print.html` 的对应区块。

**docs/ 文档（4 个，转成 `other/` 独立页面）**：

| 文件 | 内容 |
|---|---|
| `docs/strategy-v2.md` | 规则 2 胜率攻略 |
| `docs/balance-v7.md` | v7 卡牌 & 道具平衡性评估 |
| `docs/card-audit-report.md` | 卡牌公平性审计报告 |
| `docs/card-fields.md` | cards.md 字段填写说明 |

**不转**：`README.md`（仓库入口）、`LICENSE.md`、`data/README.md`、本文件（内部说明）。

## docs/ → other/ 独立页面（gen_docs）

`docs/` 下在 build.py `DOCS` 里登记的 4 篇文档会被转成 `other/` 下的独立 HTML 页面
（`other/<同名>.html`），外加索引页 `other/index.html`（标题 + 类别 + 一句话简介卡片列表）。
首页的「更多文档」入口指向索引页。

- **配置**：build.py 顶部 `DOCS = [(文档名, 类别, 一句话简介), ...]`，源是 `docs/<文档名>.md`，
  页面标题自动取 md 的一级标题（`lib/md.md_title()`），不在配置里重复写。
- **模板**：套全站风格（与 original.html 同一套米白底 / 玫红点缀），
  顶部「← 首页 / 更多文档」导航 + 标题 + 简介，页脚标注由脚本生成。
- **链接重写**：`lib/md.py` 会把相对链接折叠成相对站点根的路径（对根目录页面是对的，
  但 `other/` 是子目录）——gen_docs 后处理时把指向 docs/ 内已登记文档的链接改写成同目录 `.html`，
  其余站内相对链接（`source/` 真源、`original.html` 等）加 `../` 前缀；http(s) 与 `#` 锚点不动。
- **新增一篇文档**：md 放进 `docs/` → build.py 的 DOCS 加一行 → 跑脚本。
