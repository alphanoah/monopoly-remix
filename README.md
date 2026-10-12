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
- **电子地图 `map-print-svg.html`**：棋盘 SVG，可拖动缩放、按颜色组筛选、导出 PNG
- **打印棋盘 `map-print.html`**：80×80cm 软垫打印页，⌘/Ctrl + P →「存储为 PDF」把 PDF 交给商家
- **打印 / 电子地图共用一份真源**：`content/map-print-data.json`
- **打印页 `print.html`**：排版打印工具，选好纸张和版式直接打印；最左边可切「卡牌 / 道具」
- **在线地址**：https://alphanoah.github.io/monopoly-remix/
- **许可**：CC BY-NC 4.0，见 [LICENSE.md](LICENSE.md)

> `original.html` 是实体《大富翁》的卡牌、说明书、地图格子转录，
> 用来对照改版改了什么。照片体积太大未上传，页面里是文字版。

---

## 改完内容怎么同步

改卡牌改 `content/cards.csv`，改规则改对应的规则源文件（见下），改道具改 `content/props.md`，
改原版资料改 `content/original/*.md`，然后**跑一次脚本**：

```bash
python3 tools/update.py
```

macOS 上也可以直接双击 **`update.command`**，不用开终端。

脚本会：校验 CSV → 生成 `data/cards.json` → 重写首页的卡牌与三版规则切换区、道具清单 → 重写 `original.html` → 回写打印页内置兜底 → 解析 `content/props.md` 生成 `data/props.json` 并注入打印页道具兜底 → **校验 `content/map-print-data.json` 并把它的兜底写进两个地图页** → **按真源刷新首页「电子地图」区和 README 的「数据速览」**。
push 之后 GitHub Actions 跑的是同一个脚本，所以线上和本地永远一致。

> 校验不通过就不写任何文件，终端会指出第几行错在哪。

---

## 数据怎么改

卡牌内容的**唯一来源是 `content/cards.csv`**，不要再改 md 里的表格，也不要手改 `index.html` 里的数据块。

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
| 原版 | `content/original/manual.md` | 实体《大富翁世界之旅（银牌）》说明书转录 |
| v1 | `content/rules.md` | 第一次改版（19580 起始资金那一版） |
| v2 | `content/new-rule.md` | 最新改版，首页默认打开的就是它 |

道具清单改 `content/props.md`（首页「道具清单」区由它生成，打印页的道具卡也由它生成）。
`content/original/` 下的原版资料也是一样：改 md，跑脚本，`original.html` 就会更新。

---

## 两个页面的数据来源

| 页面 | 首页 index.html | 打印页 print.html |
|---|---|---|
| 内容 | 脚本静态写入，离线可看 | 线上 `fetch('data/cards.json')` |
| 本地双击 | 正常（内容已写死在页面里） | 正常（fetch 被 CORS 拦 → 回退内置兜底） |
| 版本切换 | 有（版本清单见下方「数据速览」） | 有（需线上 JSON） |

打印页保留双轨是因为本地 `file://` 打开时浏览器会拦截 fetch，内置兜底是必需品而不是摆设；
首页不需要，内容直接由脚本写进 HTML，本地线上都一样。

地图那两个页 fetch 的是同一份 `content/map-print-data.json`（**改棋盘只改这一份**），
本地双击打开时各自用脚本注入的内置兜底。

打印页保留双轨是因为本地 `file://` 打开时浏览器会拦截 fetch，内置兜底是必需品而不是摆设；
首页不需要，内容直接由脚本写进 HTML，本地线上都一样。

地图两个页 fetch 的是同一个 `content/map-print-data.json`（**改数据只改这一份**），
本地双击打开时各自用脚本注入的内置兜底。

---

## 数据速览

<!-- STATS:START -->
> 这一节由 <code>tools/update.py</code> 从各真源统计后写入，改了 CSV / md / JSON 跑一次脚本就会同步，**不要手改**。

| 项目 | 数量 |
|------|------|
| 卡牌 | 4 个版本（v4、v5、v6、v7），默认 <code>v7</code><br>v4 20+20 · v5 20+20 · v6 20+20 · v7 20+20 |
| 道具 | 14 件，使用规则 3 条 |
| 棋盘格子 | 64 格<br>51 地产 · 3 机会 · 3 命运 · 3 海洋 · 4 角落 |
| 颜色组 | 11 组 |
| 地价 | 共 51 块地产，均价 $2,110（$600 ~ $4,000） |
| 实物尺寸 | 80×80 cm 软垫（800×800 mm，2mm 厚 / 3mm 锁边） |
<!-- STATS:END -->

---

## 日常流程：改完内容怎么上线

```bash
# 1. 改内容（任选）
#    卡牌   → content/cards.csv
#    规则   → content/new-rule.md（v2）/ content/rules.md（v1）/ content/original/manual.md（原版）
#    道具   → content/props.md
#    原版   → content/original/*.md

# 2. 本地重新生成（macOS 也可以直接双击 update.command）
python3 tools/update.py

# 3. 提交（推送等确认后再做）
git add -A && git commit -m "改了什么"
git push
```

默认**只提交到本地**，确认没问题了再 push。

push 之后 `.github/workflows/build-pages.yml` 会在 GitHub 上再跑一次同一个脚本，
把重新生成的 `data/cards.json` / `data/props.json` / `README.md` / `index.html` / `original.html` / `print.html` / `map-print.html` / `map-print-svg.html` 自动提交回去，
然后 Pages 自动部署，约 1 分钟线上生效。

**即使你忘了跑第 2 步也没关系**——Actions 会自己跑一遍并补提交，本地文件下次 pull 就能同步回来。
本地跑的好处是能立刻看到结果、校验报错也能当场发现。

## 首次搭建 Pages（已经配好，留档备查）

仓库是 **public**，Pages 和 Actions 都已开启：

| 项目 | 设置 |
|---|---|
| Pages | Settings → Pages → Deploy from a branch → `main` / `/ (root)` |
| Actions 权限 | Settings → Actions → General → Workflow permissions → **Read and write** |
| Actions 自动触发 | 改了 `content/cards.csv` / `content/rules.md` / `content/new-rule.md` / `content/props.md` / `content/original/**` / `tools/update.py` 时 |
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
├── map-print-svg.html      电子地图：棋盘 SVG，可拖动缩放、按颜色组筛选、导出 PNG（脚本回写兜底）
│                           · 两种布局：`thick` 加厚环（340×340 正方，边格 12×80，手机可读）/ `classic` 原版（76×100 竖长格，1310×1718）
│                           · 两档结构相同（每边 16 格、角格在四角、顺时针），只有画法不同；改加厚环的环厚只动常量 RING_T（1~8）
│                           · 加厚环视图固定（不缩放不平移，手指滑到棋盘上照常滚页面）；原版布局才可缩放拖动
├── map-print.html          80×80cm 软垫打印页：⌘/Ctrl + P →「存储为 PDF」，把 PDF 交给商家（脚本回写兜底）
│                           · 页码尺寸是读取的：改 map-print-data.json 的 `board.printMM`，@page、提示条、首页文案一起变
├── update.command          macOS 双击运行 update.py
├── README.md
├── LICENSE.md              CC BY-NC 4.0
├── content/                ← 手写真源：要改东西就改这里（详见下表）
├── data/                   ← 脚本生成：cards.json / props.json，勿手改（见 data/README.md）
├── docs/                   ← 使用说明（纯文档，不参与生成）
├── tools/
│   └── update.py           一键更新：content/ → data/ + 首页 + 原版页 + 打印页
└── .github/workflows/      content/ 下真源变更时自动重生成
```

`photos/`（原版实体照片 13.8MB）不上传仓库，仅本地保留。

### `content/` 里都是什么（真源）

| 文件 | 是什么 | 谁在用 |
|---|---|---|
| `cards.csv` | **卡牌数据真源**（当前 v4–v7 四版，每版的张数见下方速览） | 生成 `data/cards.json`；打印页线上读它 |
| `new-rule.md` | **规则 v2 真源**（最新改版：地图、骰子、资金、地产、监狱、拍卖、道具、机会/命运） | 首页「游戏规则」默认打开的面板，脚本生成 |
| `rules.md` | **规则 v1 真源**（初版改版，19580 起始资金那一版） | 首页「游戏规则」的 v1 面板，脚本生成 |
| `props.md` | **道具清单**：每件道具的价格 / 效果 / 印量，以及商店买卖规则（件数见下方速览） | 首页「道具清单」区 + `data/props.json`，脚本生成 |
| `map-print-data.json` | **棋盘唯一真源**：64 格（名字/首都/价格/位置）+ 11 个颜色组（带 id 与照片取色的 hex）+ 版式参数 + 牌堆配色 + 格子类型表 | `map-print.html`（80cm 打印页）与 `map-print-svg.html`（电子地图）共用：线上 `fetch`，本地打开用各自内置的兜底（由 `tools/update.py` 注入） |
| `original/` | 原版实体《大富翁》的电子化存档（`original.html` 由它生成，见下表） | 脚本生成 |

### `content/original/` 里都是什么

| 文件 | 是什么 | 谁在用 |
|---|---|---|
| `manual.md` | 原版《大富翁世界之旅（银牌）》说明书的照片转录（准备、骰子、起点、地产、房屋、监狱、抵押、破产……） | `original.html` 的说明书区块；同时是首页「游戏规则」的原版面板 |
| `cards.md` | 原版命运牌 & 机会牌各 20 张的转录（牌面文字 + 金额） | `original.html` 的卡牌区块 |
| `map-data-guide.md` | 地图数据的使用指南：速览、投资建议、FAQ | `original.html` 的折叠区块（默认收起） |
| `map-tiles.md` | 原版地图 64 格原始数据（格名、颜色组、价格、特殊格） | `original.html` 的折叠区块（默认收起） |

> 目录里的 `.DS_Store` 是 macOS 自己生成的，已被 `.gitignore` 排除，不用管。

### `docs/` 里都是什么（纯说明，不参与生成）

| 文件 | 是什么 |
|---|---|
| `csv-fields.md` | `content/cards.csv` 每一列怎么填、对应 JSON 哪个字段、脚本会拦哪些错 |
| `card-diff.md` | 新版 40 张自制牌 vs 原版 40 张牌的逐张差异对照 |

