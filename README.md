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

## 网站上有什么

线上地址：https://alphanoah.github.io/monopoly-remix/ （GitHub Pages，main 分支根目录部署）

- **首页 `index.html`**：现在在玩的规则是 **v3**（`source/remix/manual-v3.md` 生成，默认打开）。
  页面从上到下五块：①「为什么要改这一版」改版背景；②「游戏规则」四版并列（原版 / v1 / v2 / v3），
点卡片切换，**默认 v3**；③「机会/命运卡牌」自制卡牌全文，可按版本切换浏览（当前 v7，共 4 版）；
  ④「道具清单」14 件道具与商店规则；⑤「打印」「电子地图」「原版资料」「更多文档」四个入口。
- **电子地图 `map.html`**：棋盘 SVG，两档视图 ——
  **打印版**（按实体棋盘一比一还原的 80×80cm 软垫图，点「打印」直接出 800×800mm）、
  **放大版**（同一张图，跑道加厚吃进中间空、文字竖排放大，手机上也能看清）。
  两档视图都固定一屏放下（不缩放不平移），可按颜色组筛选色块。
  「v2 规则地图」**默认开启**：按 `source/map.json` 里 `variants.v2` 的替换表改格子（北极→监狱、印度洋/大西洋→道具商店，赤道仍是起点），再点一次看原版地图（或直接开 `map.html#v=0`），导出文件名会带 `-v2` 标记；
  按钮按档位出现：放大版只有「导出图片」（7200×7200px PNG，80cm 成品下约 229 DPI）；
  打印版多出「打印」和「导出 SVG」（矢量文件，画布直接是 800×800mm，可给印刷商家或用 Illustrator 打开），
  并附「给商家打印」说明卡：首选打印存 PDF，商家要改图给 SVG，字体有问题给 PNG，且提醒商家直接出图别用 AI/PS 二次编辑。
- **打印 / 电子地图共用一份真源**：`source/map.json`
- **原版资料 `original.html`**：实体《大富翁》的卡牌、说明书、地图数据转录，用来对照改版改了什么
- **打印页 `print.html`**：排版打印工具，选好纸张和版式直接打印；最左边可切「卡牌 / 道具」
- **更多文档 `other/index.html`**：改版过程中的分析文档（规则审查、攻略、平衡性、卡牌审计、字段说明），由 `docs/` 下的 md 生成
- **许可**：CC BY-NC 4.0，见 [LICENSE.md](LICENSE.md)

> `original.html` 是实体《大富翁》的卡牌、说明书、地图格子转录，
> 用来对照改版改了什么。照片体积太大未上传，页面里是文字版。

---

## 改完内容怎么同步

改卡牌改 `source/cards.md`，改规则改对应的规则源文件（见下），改道具改 `source/props.md`，
改原版资料改 `source/original/*.md`，然后**跑一次脚本**：

```bash
python3 tools/build.py
```

macOS 上也可以直接双击 **`update.command`**，不用开终端。

脚本会：校验 `source/cards.md` → 生成 `data/cards.json` → 重写首页的卡牌与四版规则切换区、道具清单 → 重写 `original.html` → 回写打印页内置兜底 → 解析 `source/props.md` 生成 `data/props.json` 并注入打印页道具兜底 → **校验 `source/map.json` 并把它的兜底写进地图页 `map.html`** → **按真源刷新首页「电子地图」区和 README 的「数据速览」**。
push 之后 GitHub Actions 跑的是同一个脚本，所以线上和本地永远一致。

> 校验不通过就不写任何文件，终端会指出哪张牌错在哪。

---

## 数据怎么改

卡牌内容的**唯一来源是 `source/cards.md`**（Markdown 表格），不要手改 `index.html` 里的数据块。

结构是「版本 → 花色 → 表格」三层：`## v7 · 邪恶版 · 世界之旅（修订）` 分版本（标题整行就是页面版本下拉的显示名），
`### 机会牌` / `### 命运牌` 分花色，每节一张表：

```
| 编号 | 表情 | 事件 | 效果 | 命中率 | 启用 |        ← 机会牌
| 编号 | 事件 | 判定 | 赢 | 输 | 命中率 | 启用 |      ← 命运牌
```

每列怎么填、对应 JSON 什么字段、脚本会拦哪些错误，见 **[docs/card-fields.md](docs/card-fields.md)**。

### 编辑时注意

- 直接改 md 表格就行：金额写 `3000` 或 `+3000` 都行（脚本统一补正号），空单元格 = 该字段留空。
- 想用 Excel / Numbers 批量改：首页「机会/命运卡牌」区点「导出 CSV / Excel」→ 改完 →
  `python3 tools/import-cards.py 文件.csv` 回导成 cards.md（回导前自动校验 + 回读比对，不一致不写）。
- 改完保存 → 跑 `python3 tools/build.py` → 提交。

规则文件改哪个，首页就更新哪个，**不要在首页直接改规则**：

| 版本 | 源文件 | 说明 |
|---|---|---|
| 原版 | `source/original/manual.md` | 实体《大富翁世界之旅（银牌）》说明书转录 |
| v1 | `source/remix/manual-v1.md` | 第一次改版（19580 起始资金那一版） |
| v2 | `source/remix/manual-v2.md` | 过渡改版（回归五档房产、道具商店那一版） |
| v3 | `source/remix/manual-v3.md` | 最新改版，首页默认打开的就是它 |

道具清单改 `source/props.md`（首页「道具清单」区由它生成，打印页的道具卡也由它生成）。
`source/original/` 下的原版资料也是一样：改 md，跑脚本，`original.html` 就会更新。

---

## 页面的数据来源

| 页面 | 首页 index.html | 打印页 print.html |
|---|---|---|
| 内容 | 脚本静态写入，离线可看 | 线上 `fetch('data/cards.json')` |
| 本地双击 | 正常（内容已写死在页面里） | 正常（fetch 被 CORS 拦 → 回退内置兜底） |
| 版本切换 | 有（版本清单见下方「数据速览」） | 有（需线上 JSON） |

打印页保留双轨是因为本地 `file://` 打开时浏览器会拦截 fetch，内置兜底是必需品而不是摆设；
首页不需要，内容直接由脚本写进 HTML，本地线上都一样。

地图页 `map.html` fetch 的是 `source/map.json`（**改棋盘只改这一份**），
本地双击打开时用脚本注入的内置兜底。

---

## 数据速览

<!-- STATS:START -->
> 这一节由 <code>tools/build.py</code> 从各真源统计后写入，改了 md / JSON 真源后跑一次脚本就会同步，**不要手改**。

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
#    卡牌   → source/cards.md
#    规则   → source/remix/manual-v3.md（v3，默认）/ manual-v2.md（v2）/ manual-v1.md（v1）/ source/original/manual.md（原版）
#    道具   → source/props.md
#    原版   → source/original/*.md

# 2. 本地重新生成（macOS 也可以直接双击 update.command）
python3 tools/build.py

# 3. 提交（推送等确认后再做）
git add -A && git commit -m "改了什么"
git push
```

默认**只提交到本地**，确认没问题了再 push。

push 之后 `.github/workflows/build-pages.yml` 会在 GitHub 上再跑一次同一个脚本，
把重新生成的 `data/cards.json` / `data/props.json` / `README.md` / `index.html` / `original.html` / `print.html` / `map.html` 自动提交回去，
然后 Pages 自动部署，约 1 分钟线上生效。

**即使你忘了跑第 2 步也没关系**——Actions 会自己跑一遍并补提交，本地文件下次 pull 就能同步回来。
本地跑的好处是能立刻看到结果、校验报错也能当场发现。

## 首次搭建 Pages（已经配好，留档备查）

仓库是 **public**，Pages 和 Actions 都已开启：

| 项目 | 设置 |
|---|---|
| Pages | Settings → Pages → Deploy from a branch → `main` / `/ (root)` |
| Actions 权限 | Settings → Actions → General → Workflow permissions → **Read and write** |
| Actions 自动触发 | 改了 `source/cards.md` / `source/remix/**` / `source/props.md` / `source/original/**` / `source/map.json` / `docs/**` / `tools/**` 时 |
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
├── index.html              首页：改版背景 + 规则三版切换（原版/v1/v2，默认 v2）+ 机会/命运卡牌（v4–v7 可切）+ 道具清单 + 打印/地图/原版资料/更多文档入口（脚本生成，静态）
├── original.html           原版资料页：原版卡牌/说明书/地图（脚本生成，静态）
├── print.html              打印页：排版打印工具，可切卡牌/道具（脚本回写兜底）
├── map.html                电子地图：棋盘 SVG（脚本回写兜底）
│                           · 两档布局：打印版（80cm 软垫图一比一还原，页码尺寸读 map.json 的 `board.printMM`）/ 放大版（board.zoomTrackWidth 控制跑道加厚程度，文字竖排、正立不旋转）
│                           · 两档结构相同（每边 15 格 + 4 个角格、角格在四角、顺时针），只有画法不同
│                           · 视图固定一屏放下（不缩放不平移）；可按颜色组筛选、导出 PNG
├── update.command          macOS 双击运行 tools/build.py
├── README.md
├── LICENSE.md              CC BY-NC 4.0
├── source/                ← 手写真源：要改东西就改这里（详见下表）
├── data/                   ← 脚本生成：cards.json / props.json，勿手改（见 data/README.md）
├── docs/                   ← 手写真源：攻略 / 平衡性 / 卡牌对照等文档（详见下表）
├── other/                  ← 脚本生成：docs/ 的 HTML 版 + 索引页，勿手改
├── tools/
│   ├── build.py            一键更新入口：source/ → data/ + 首页 + 原版页 + 打印页 + 地图页 + README 速览
│   │                       · python3 tools/build.py              全部跑一遍
│   │                       · python3 tools/build.py --step gen_pages   只跑某一步
│   ├── import-cards.py     卡牌 CSV → source/cards.md 回导（配合首页「导出」按钮批量编辑）
│   ├── steps/              六个构建步骤：validate / gen_data / gen_pages / gen_map / gen_docs / gen_readme
│   └── lib/                公共模块：cards / props / mapdata 解析、md→HTML、标记块替换、路径
├── sim/                    ← 对局模拟，独立于构建链
│   ├── sim-v2.py           规则 2 模拟：落点分布 + 组经济 + 起点口径对照（python3 sim/sim-v2.py）
│   └── game.py             规则 2 完整对局模拟：8 人混战，含 14 件道具与全部 v7 卡牌
│                           · python3 sim/game.py             单配置（夺冠率）
│                           · AB=1 python3 sim/game.py        「道具 × 监狱口径」2×2 对照
│                           · COHORT=1 python3 sim/game.py    「集中同色 vs 到处撒」A/B
│                           · AUDIT=1 python3 sim/game.py     逐张卡牌实战净值插桩 + 8 人局节奏
│                             （加 PROP_UNLIMITED=1 跑道具不限量对照、JAIL_NO_RENT=0 关坐牢免租）
└── .github/workflows/      source/ 下真源变更时自动重生成
```

`photos/`（原版实体照片 13.8MB）不上传仓库，仅本地保留。

### `source/` 里都是什么（真源）

| 文件 | 是什么 | 谁在用 |
|---|---|---|
| `cards.md` | **卡牌数据真源**（当前 v4–v7 四版，每版的张数见下方速览） | 生成 `data/cards.json`；打印页线上读它 |
| `remix/manual-v3.md` | **规则 v3 真源**（最新改版：破产 / 胜利条件闭环、坐牢与道具上限修复、16 张牌池抽卡、踩自己地才能买 / 升） | 首页「游戏规则」默认打开的面板，脚本生成 |
| `remix/manual-v2.md` | **规则 v2 真源**（过渡改版：回归五档房产与 15000 资金、道具商店、出狱手段道具化） | 首页「游戏规则」的 v2 面板，脚本生成 |
| `remix/manual-v1.md` | **规则 v1 真源**（初版改版，19580 起始资金那一版） | 首页「游戏规则」的 v1 面板，脚本生成 |
| `props.md` | **道具清单**：每件道具的价格 / 效果 / 印量，以及商店买卖规则（件数见下方速览） | 首页「道具清单」区 + `data/props.json`，脚本生成 |
| `map.json` | **棋盘唯一真源**：64 格（名字/国旗 emoji/首都/价格/位置）+ 11 个颜色组（带 id 与照片取色的 hex）+ 版式参数 + 牌堆配色 + 格子类型表 | `map.html`（电子地图 + 80cm 打印版，一个页面两档布局）共用：线上 `fetch`，本地打开用内置兜底（由 `tools/build.py` 注入） |
| `original/` | 原版实体《大富翁》的电子化存档（`original.html` 由它生成，见下表） | 脚本生成 |

### `source/original/` 里都是什么

| 文件 | 是什么 | 谁在用 |
|---|---|---|
| `manual.md` | 原版《大富翁世界之旅（银牌）》说明书的照片转录（准备、骰子、起点、地产、房屋、监狱、抵押、破产……） | `original.html` 的说明书区块；同时是首页「游戏规则」的原版面板 |
| `cards.md` | 原版命运牌 & 机会牌各 20 张的转录（牌面文字 + 金额） | `original.html` 的卡牌区块 |
| `map-data-guide.md` | 地图数据的使用指南：怎么读懂格子/分组/轨道、投资建议、FAQ、开发字段说明 | `original.html` 的折叠区块（默认收起）；统计表格由脚本插入 |
| `map-tiles.md` | 地图 64 格全表：概览、11 个颜色组明细、汇总排序、价位分布、四边轨道 | 同上；**正文只剩说明文字，所有表格由 build.py 从 map.json 遍历生成** |

> 目录里的 `.DS_Store` 是 macOS 自己生成的，已被 `.gitignore` 排除，不用管。

### `docs/` 里都是什么（真源，脚本转成 `other/` 下的 HTML 页面）

| 文件 | 是什么 |
|---|---|
| `card-fields.md` | `source/cards.md` 每个字段怎么填、对应 JSON 哪个字段、脚本会拦哪些错、Excel 批量编辑怎么回导 |
| `strategy-v2.md` | **规则 2** 的胜率攻略：统一起点后的残余落点偏差（≤±5%）、连锁机制的 K 倍放大器、完整对局模拟夺冠率排名、14 件道具的「加速 + 反领先」效应、监狱口径 A/B |
| `balance-v7.md` | **v7 卡牌 & 道具平衡性评估**：40 张牌的实战净值实测（哪张不公平）、道具价格/数量（供给只满足 45% 需求）、8 人局节奏与时长（约 979 次行动 ≈ 5.5-12 小时）、「坐牢在规则 2 里是免费的」这一系统性漏洞 |

