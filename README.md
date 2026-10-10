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

- **首页 `index.html`**：改版规则 + 卡牌全文，可切换版本浏览（静态页面，双击就能看）
- **原版资料 `original.html`**：实体《大富翁》的卡牌、说明书、地图数据转录
- **打印页 `print.html`**：排版打印工具，选好纸张和版式直接打印
- **在线地址**：https://alphanoah.github.io/monopoly-remix/
- **许可**：CC BY-NC 4.0，见 [LICENSE.md](LICENSE.md)

> `original.html` 是实体《大富翁》的卡牌、说明书、地图格子转录，
> 用来对照改版改了什么。照片体积太大未上传，页面里是文字版。

---

## 改完内容怎么同步

改卡牌改 `cards.csv`，改规则改 `docs/rules.md`，改原版资料改 `original/*.md`，然后**跑一次脚本**：

```bash
python3 tools/update.py
```

macOS 上也可以直接双击 **`update.command`**，不用开终端。

脚本会：校验 CSV → 生成 `cards.json` → 重写首页的卡牌与规则 → 重写 `original.html` → 回写打印页内置兜底。
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
| `version` | 版本号，如 `v6`。加新版本就新增一批行 |
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
- 改完保存 → 跑 `python3 tools/update.py` → push。

规则改 `docs/rules.md` 同理，首页规则区是从它生成的，**不要在首页直接改规则**。
`original/` 下的原版资料也是一样：改 md，跑脚本，`original.html` 就会更新。

---

## 两个页面的数据来源

| 页面 | 首页 index.html | 打印页 print.html |
|---|---|---|
| 内容 | 脚本静态写入，离线可看 | 线上 `fetch('cards.json')` |
| 本地双击 | 正常（内容已写死在页面里） | 正常（fetch 被 CORS 拦 → 回退内置兜底） |
| 版本切换 | 有，v4 / v5 / v6 | 有（需线上 JSON） |

打印页保留双轨是因为本地 `file://` 打开时浏览器会拦截 fetch，内置兜底是必需品而不是摆设；
首页不需要，内容直接由脚本写进 HTML，本地线上都一样。

---

## 日常流程：改完内容怎么上线

```bash
# 1. 改内容（任选）
#    卡牌   → cards.csv
#    规则   → docs/rules.md
#    原版   → original/*.md

# 2. 本地重新生成（macOS 也可以直接双击 update.command）
python3 tools/update.py

# 3. 提交并推送
git add -A && git commit -m "改了什么" && git push
```

push 之后 `.github/workflows/build-pages.yml` 会在 GitHub 上再跑一次同一个脚本，
把重新生成的 `cards.json` / `index.html` / `original.html` / `print.html` 自动提交回去，
然后 Pages 自动部署，约 1 分钟线上生效。

**即使你忘了跑第 2 步也没关系**——Actions 会自己跑一遍并补提交，本地文件下次 pull 就能同步回来。
本地跑的好处是能立刻看到结果、校验报错也能当场发现。

## 首次搭建 Pages（已经配好，留档备查）

仓库是 **public**，Pages 和 Actions 都已开启：

| 项目 | 设置 |
|---|---|
| Pages | Settings → Pages → Deploy from a branch → `main` / `/ (root)` |
| Actions 权限 | Settings → Actions → General → Workflow permissions → **Read and write** |
| Actions 自动触发 | 改了 `cards.csv` / `docs/rules.md` / `original/**` / `tools/update.py` 时 |
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
├── index.html              首页：规则 + 卡牌浏览（脚本生成，静态）
├── original.html           原版资料页：原版卡牌/说明书/地图（脚本生成，静态）
├── print.html              打印页：排版打印工具（脚本回写兜底）
├── cards.csv               卡牌数据真源
├── cards.json              由 cards.csv 生成，供打印页读取
├── update.command          macOS 双击运行 update.py
├── README.md
├── LICENSE.md              CC BY-NC 4.0
├── docs/
│   ├── rules.md            改版规则真源（首页规则区由它生成，含初版卡牌留档）
│   ├── csv-fields.md       cards.csv 每列的填法与对应 JSON 字段
│   └── card-diff.md        新版 vs 原版差异对照
├── original/               原版实体《大富翁》的电子化存档（original.html 由它生成）
│   ├── cards.md            原版命运牌 & 机会牌（20 + 20）转录
│   ├── manual.md           原版《大富翁世界之旅（银牌）》说明书转录
│   ├── map-data-guide.md   地图数据使用指南（速览 / 投资建议 / FAQ）
│   └── map-tiles.md        原版地图 64 格原始数据
├── cards/                  自制卡牌历史版本存档 v1–v6.md
├── tools/
│   ├── update.py           一键更新：CSV → JSON + 首页 + 打印页
│   └── md2csv.py           一次性迁移脚本：cards/vN.md → cards.csv
└── .github/workflows/      cards.csv / docs/rules.md / original/ 变更时自动重生成
```

`photos/`（原版实体照片 13.8MB）不上传仓库，仅本地保留。
