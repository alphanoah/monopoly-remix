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
| `import-cards.py` | 卡牌 CSV → `source/remix/cards.md` 回导（配合首页「导出 CSV / Excel」批量编辑；校验 + 回读比对，不一致不写） |
| `steps/validate.py` | 校验真源：卡牌硬失败（不写任何文件），棋盘/道具软失败（跳过相关块） |
| `steps/gen_data.py` | 生成 `data/cards.json`、`data/props.json` |
| `steps/gen_pages.py` | 重写 `index.html` / `original.html` / `print.html` 的标记块 |
| `steps/gen_map.py` | 回写 `map.html` 的地图兜底数据 |
| `steps/gen_docs.py` | 把 `docs/` 下的文档转成 `other/` 独立页面 + 索引页（见下） |
| `steps/gen_readme.py` | 刷新 `README.md` 的「数据速览」块 |
| `lib/md.py` | 简易 md → HTML（标题/列表/引用/表格/链接/粗体/行内码） |
| `lib/docs.py` | 扫描 `docs/` 目录 + 解析 md 头顶的元数据注释（分类 / 简介 / 排序 / 状态） |
| `lib/cards.py` | cards.md 三层结构（版本→花色→表格）的解析 / 校验 / 生成 |
| `lib/mapdata.py` | `source/remix/map.json` 的解析与统计表生成 |
| `lib/props.py` | `source/remix/props.md` 道具清单解析 |
| `lib/html_block.py` | 标记块替换（`<!-- XXX:START -->...<!-- XXX:END -->`），手改部分不动 |
| `lib/ctx.py` | 步骤间共享的真源缓存（按需加载） |
| `lib/paths.py` | 全部路径常量 |

## 真源 → 产物链路

| 真源（手写） | 产物（脚本生成，勿手改） |
|---|---|
| `source/remix/cards.md` | `data/cards.json` + `index.html` 卡牌区 + `print.html` 兜底 |
| `source/remix/manual-v3.md`（v3，现行）| `index.html` 规则 tab（默认打开） |
| `source/remix/manual-v2.md`（v2，过渡）| `index.html` 规则 tab |
| `source/remix/manual-v1.md`（v1，朋友初版）| `index.html` 规则 tab |
| `source/original/manual.md` | `index.html` 原版 tab + `original.html` |
| `source/original/cards.md` | `original.html` |
| `source/original/map-data-guide.md` | `original.html` 折叠区块（统计表由脚本现算插入） |
| `source/original/map-tiles.md` | `original.html` 折叠区块（同上） |
| `source/remix/props.md` | `index.html` 道具区 + `data/props.json` + `print.html` 兜底 |
| `source/remix/map.json` | `map.html` 兜底 + `index.html` 地图区 + README 速览 |
| `docs/*.md`（扫描目录得来，不用登记） | `other/<同名>.html` + `other/index.html` 索引页 |

产物页面里只有 `<!-- XXX:START/END -->` 标记块内的内容会被脚本覆盖，块外的手写部分（页面骨架、样式、交互 JS）不受影响。

## 仓库 md 统计

**已入构建链（9 个）**：上表左侧全部。它们不是独立页面，而是注入
`index.html` / `original.html` / `print.html` 的对应区块。

**docs/ 文档（6 个，转成 `other/` 独立页面）**：

| 文件 | 内容 |
|---|---|
| `docs/strategy-v2.md` | 规则 2 胜率攻略（历史：结论已被 v3 取代） |
| `docs/rule-changelog.md` | 规则修订记录：v2 审查 → v3 落地（17 条建议 + 逐条去向） |
| `docs/balance-v7.md` | v7 卡牌 & 道具平衡性评估 |
| `docs/card-audit-report.md` | 卡牌公平性审计报告 |
| `docs/card-fields.md` | cards.md 字段填写说明 |

**不转**：`README.md`（仓库入口）、`LICENSE.md`、`data/README.md`、本文件（内部说明）。

## docs/ → other/ 独立页面（gen_docs）

**`docs/` 下的 md 全部会被扫描**并转成 `other/` 下的独立 HTML 页面（`other/<同名>.html`），
外加按分类分层的索引页 `other/index.html`。首页的「更多文档」入口指向索引页。

- **不用登记清单**：以前要在 build.py 的 `DOCS` 里登记，漏登记就没有页面；现在直接扫描目录，
  漏之子不可能再发生。`_` 开头的是草稿，跳过不发布。
- **元数据写在 md 自己身上**（md 顶部的单行 HTML 注释，`lib/docs.py` 解析）：
  `<!-- cat: 分类 -->`、`<!-- blurb: 一句话简介 -->`、`<!-- order: 排序号 -->`、`<!-- status: 状态提示 -->`。
  写在 md 里 = 单一真源，改文档和改描述是同一个动作。
- **模板**：套全站风格（与 original.html 同一套米白底 / 玫红点缀），
  顶部「← 首页 / 更多文档」导航 + 标题 + 简介 + 状态提示条，页脚标注由脚本生成。
- **链接重写**：`lib/md.py` 会把相对链接折叠成相对站点根的路径（对根目录页面是对的，
  但 `other/` 是子目录）——gen_docs 后处理时把指向 docs/ 内文档的链接改写成 `other/<同名>.html`，
  其余站内相对链接（`source/` 真源、`original.html` 等）加 `../` 前缀；http(s) 与 `#` 锚点不动。
  gen_pages 的规则区用同一套映射（`lib/docs.doc_map()`）。
- **新增一篇文档**：md 丢进 `docs/`（写好 cat/blurb 两个注释）→ 跑脚本。删掉或改名 md，对应的 html 自动清理。

