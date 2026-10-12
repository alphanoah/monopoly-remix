# 大富翁改版 · 规则与自制卡牌

在实体《大富翁》基础上重做的一套玩法：**规则改了，卡牌也改了**。
单个十六面骰、19580 起始资金，房子、过路费、监狱、拍卖规则全部重写，机会牌与命运牌 40 张换成自制的。

## 为什么会有这一版

7 个非常熟的朋友凑一桌，大部分人第一次玩。晚上开局，**整整四个小时没打完**，最后实在太晚，
临时加了一条「跑毒」——每一轮结束每个玩家各扣 2000，才把结局逼出来。

回头看问题很清楚：钱和过路费确实在指数增长，但**节奏太慢**，四个小时过去了没人盖起后期的高级房子，
最好玩的那一段一直玩不到。

所以这一版的核心目标就是**把节奏拧快**：十六面骰拉大每一步的跨度、起始资金一次给足到 19580、
过路费和房子等级重算，让后期的高级房子更早登场；卡牌顺势改成损人利己 + 押注博弈，熟人局才玩得出味道。

- **首页 `index.html`**：三版规则卡片切换（原版 / v1 / v2）+ 机会/命运卡牌 + 道具清单，卡牌可切换版本浏览（静态页面，双击就能看）
- **原版资料 `original.html`**：实体《大富翁》的卡牌、说明书、地图数据转录
- **电子地图 `map-svg.html`**：64 格 SVG 棋盘，可拖动缩放、按颜色组筛选、导出 PNG
- **打印页 `print.html`**：排版打印工具，选好纸张和版式直接打印；最左边可切「卡牌 / 道具」
- **在线地址**：https://alphanoah.github.io/monopoly-remix/
- **许可**：CC BY-NC 4.0，见 [LICENSE.md](LICENSE.md)

> `original.html` 是实体《大富翁》的卡牌、说明书、地图格子转录，
> 用来对照改版改了什么。照片体积太大未上传，页面里是文字版。

---

## 改完内容怎么同步

改卡牌改 `cards.csv`，改规则改对应的规则源文件（见下），改道具改 `docs/props.md`，
改原版资料改 `original/*.md`，然后**跑一次脚本**：

```bash
python3 tools/update.py
```

macOS 上也可以直接双击 **`update.command`**，不用开终端。

脚本会：校验 CSV → 生成 `cards.json` → 重写首页的卡牌与三版规则切换区、道具清单 → 重写 `original.html` → 回写打印页内置兜底 → 解析 `props.md` 生成 `props.json` 并注入打印页道具兜底。
push 之后 GitHub Actions 跑的是同一个脚本，所以线上和本地永远一致。

> 校验不通过就不写任何文件，终端会指出第几行错在哪。

---

## 数据怎么改

卡牌内容的**唯一来源是 `cards.csv`**，不要再改 md 里的表格，也不要手改 `index.html` 里的数据块。

```
version,deck,seq,face,event,effect,cond,win,lose,rate,use
```

| 列 | 说明 |
|---|---|
| `version` | 版本号，如 `v7`。加新版本就新增一批行 |
| `deck` | `chance`（机会）或 `fate`（命运） |
| `seq` | 牌面编号，从 1 开始 |
| `face` | 机会牌专用：`smile` 奖励 / `frown` 惩罚（决定卡面表情） |
| `event` | 卡面正文（事件描述） |
| `effect` | 机会牌专用：效果文字 |
| `cond` / `win` / `lose` | 命运牌专用：判定方式 / 赢了怎样 / 输了怎样 |
| `rate` | 命中率，只作备注，不参与渲染 |
| `use` | `1` 采用、`0` 弃用。填 `0` 的牌不会出现在页面里 |

每列怎么填、对应 JSON 什么字段、脚本会拦哪些错误，见 **[docs/csv-fields.md](docs/csv-fields.md)**。

### 编辑时注意

- 用 Excel / Numbers 打开后**必须存成「CSV UTF-8（带 BOM）」**，否则中文会乱码。
  macOS 的 Numbers 导出时选「CSV」一般就是 UTF-8；Excel 另存时要挑「CSV UTF-8(逗号分隔)」那个选项。
- 单元格里可以正常写逗号和引号，Excel 保存时会自动加转义。
- 改完保存 → 跑 `python3 tools/update.py` → 提交。

规则文件改哪个，首页就更新哪个，**不要在首页直接改规则**：

| 版本 | 源文件 | 说明 |
|---|---|---|
| 原版 | `original/manual.md` | 实体《大富翁世界之旅（银牌）》说明书转录 |
| v1 | `docs/rules.md` | 第一次改版（19580 起始资金那一版） |
| v2 | `docs/new-rule.md` | 最新改版，首页默认打开的就是它 |

道具清单改 `docs/props.md`（首页「道具清单」区由它生成，打印页的道具卡也由它生成）。
`original/` 下的原版资料也是一样：改 md，跑脚本，`original.html` 就会更新。

---

## 两个页面的数据来源

| 页面 | 首页 index.html | 打印页 print.html |
|---|---|---|
| 内容 | 脚本静态写入，离线可看 | 线上 `fetch('cards.json')` |
| 本地双击 | 正常（内容已写死在页面里） | 正常（fetch 被 CORS 拦 → 回退内置兜底） |
| 版本切换 | 有，v4 / v5 / v6 / v7（默认 v7） | 有（需线上 JSON） |

打印页保留双轨是因为本地 `file://` 打开时浏览器会拦截 fetch，内置兜底是必需品而不是摆设；
首页不需要，内容直接由脚本写进 HTML，本地线上都一样。

---

## 日常流程：改完内容怎么上线

```bash
# 1. 改内容（任选）
#    卡牌   → cards.csv
#    规则   → docs/new-rule.md（v2）/ docs/rules.md（v1）/ original/manual.md（原版）
#    道具   → docs/props.md
#    原版   → original/*.md

# 2. 本地重新生成（macOS 也可以直接双击 update.command）
python3 tools/update.py

# 3. 提交（推送等确认后再做）
git add -A && git commit -m "改了什么"
git push
```

默认**只提交到本地**，确认没问题了再 push。

push 之后 `.github/workflows/build-pages.yml` 会在 GitHub 上再跑一次同一个脚本，
把重新生成的 `cards.json` / `props.json` / `index.html` / `original.html` / `print.html` 自动提交回去，
然后 Pages 自动部署，约 1 分钟线上生效。

**即使你忘了跑第 2 步也没关系**——Actions 会自己跑一遍并补提交，本地文件下次 pull 就能同步回来。
本地跑的好处是能立刻看到结果、校验报错也能当场发现。

## 首次搭建 Pages（已经配好，留档备查）

仓库是 **public**，Pages 和 Actions 都已开启：

| 项目 | 设置 |
|---|---|
| Pages | Settings → Pages → Deploy from a branch → `main` / `/ (root)` |
| Actions 权限 | Settings → Actions → General → Workflow permissions → **Read and write** |
| Actions 自动触发 | 改了 `cards.csv` / `docs/rules.md` / `docs/new-rule.md` / `docs/props.md` / `original/**` / `tools/update.py` 时 |
| 手动触发 | Actions → 重新生成页面 → Run workflow |

> Actions 的写权限是**必须的**：workflow 要把生成的文件提交回仓库，只读权限会失败。

---

## 打印设置

- 纸张：6 寸相片纸（横放，152×102mm，默认）或 A4
- 边距：**无**；缩放：**100%**（不要选「适应页面」）
- 勾选「**背景图形**」，否则卡底色印不出来
- 印背面：先印正面 → 整叠翻面 → 印背面。页面会自动处理翻面镜像的格子对齐

---

## 目录

```
richer/
├── index.html              首页：规则三版切换（原版/v1/v2）+ 机会/命运卡牌 + 道具清单（脚本生成，静态）
├── original.html           原版资料页：原版卡牌/说明书/地图（脚本生成，静态）
├── print.html              打印页：排版打印工具，可切卡牌/道具（脚本回写兜底）
├── props.json              道具数据（由 docs/props.md 生成，打印页用）
├── map-svg.html            电子地图：64 格 SVG 棋盘，一键切换「加厚环（手机好读）/ 原版」，可导出 PNG，图例可点击筛选（手写页，脚本不动）
│                           · 两种布局：`thick` 加厚环（340×340 正方，边格 12×80，手机可读）/ `classic` 原版（76×100 竖长格，1310×1718）
│                           · 两档结构相同（每边 16 格、角格在四角、顺时针），只有画法不同；改加厚环的环厚只动常量 RING_T（1~8）
│                           · 加厚环视图固定（不缩放不平移，手指滑到棋盘上照常滚页面）；原版布局才可缩放拖动
├── cards.csv               卡牌数据真源
├── cards.json              由 cards.csv 生成，供打印页读取
├── update.command          macOS 双击运行 update.py
├── README.md
├── LICENSE.md              CC BY-NC 4.0
├── docs/                   规则 / 道具 / 字段说明 / 地图数据 / 卡牌差异（详见下表）
├── original/               原版实体《大富翁》的电子化存档（original.html 由它生成）
├── tools/
│   └── update.py           一键更新：CSV → JSON + 首页 + 原版页 + 打印页
└── .github/workflows/      cards.csv / docs 规则 / original/ 变更时自动重生成
```

`photos/`（原版实体照片 13.8MB）不上传仓库，仅本地保留。

### `docs/` 里都是什么

| 文件 | 是什么 | 谁在用 |
|---|---|---|
| `new-rule.md` | **规则 v2 真源**（最新改版：地图、骰子、资金、地产、监狱、拍卖、道具、机会/命运） | 首页「游戏规则」默认打开的面板，脚本生成 |
| `rules.md` | **规则 v1 真源**（初版改版，19580 起始资金那一版） | 首页「游戏规则」的 v1 面板，脚本生成 |
| `props.md` | **道具清单**：14 件道具的价格 / 效果 / 印量，以及商店买卖规则 | 首页「道具清单」区，脚本生成 |
| `csv-fields.md` | `cards.csv` 每一列怎么填、对应 JSON 哪个字段、脚本会拦哪些错 | README 与首页 v1 规则里的链接（纯文档） |
| `card-diff.md` | 新版 40 张自制牌 vs 原版 40 张牌的逐张差异对照 | 首页与原版资料页的页脚链接（纯文档） |
| `map-data.json` | 电子地图 64 格数据（格名、颜色组、地价） | `map-svg.html` 线上 `fetch`；本地打开时用它内置的同款兜底 |

### `original/` 里都是什么

| 文件 | 是什么 | 谁在用 |
|---|---|---|
| `manual.md` | 原版《大富翁世界之旅（银牌）》说明书的照片转录（准备、骰子、起点、地产、房屋、监狱、抵押、破产……） | `original.html` 的说明书区块；同时是首页「游戏规则」的原版面板 |
| `cards.md` | 原版命运牌 & 机会牌各 20 张的转录（牌面文字 + 金额） | `original.html` 的卡牌区块 |
| `map-data-guide.md` | 地图数据的使用指南：速览、投资建议、FAQ | `original.html` 的折叠区块（默认收起） |
| `map-tiles.md` | 原版地图 64 格原始数据（格名、颜色组、价格、特殊格） | `original.html` 的折叠区块（默认收起） |

> 两个目录里的 `.DS_Store` 是 macOS 自己生成的，已被 `.gitignore` 排除，不用管。

