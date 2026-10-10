# 大富翁 · 自制机会 / 命运卡牌

在实体《大富翁》基础上改的一套玩法：单个十六面骰、19580 起始资金，机会牌与命运牌全部重写。

- **首页 `index.html`**：规则 + 卡牌全文，可切换版本浏览（静态页面，双击就能看）
- **打印页 `print.html`**：排版打印工具，选好纸张和版式直接打印
- **在线地址**：开启 Pages 后为 `https://<用户名>.github.io/<仓库名>/`
- **许可**：CC BY-NC 4.0，见 [LICENSE.md](LICENSE.md)

---

## 改完内容怎么同步

改卡牌改 `cards.csv`，改规则改 `docs/rules.md`，然后**跑一次脚本**：

```bash
python3 tools/update.py
```

macOS 上也可以直接双击 **`update.command`**，不用开终端。

脚本会：校验 CSV → 生成 `cards.json` → 重写首页的卡牌与规则 → 回写打印页内置兜底。
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

## 开启 GitHub Pages

1. 仓库设为 **public**
2. Settings → **Pages** → Source 选 **Deploy from a branch**
3. Branch 选 `main`、目录选 `/ (root)` → Save
4. 首次发布等 1-2 分钟，Actions 页面可以看部署进度

如果 Actions 自动提交失败，检查 Settings → Actions → General → **Workflow permissions** 是否选了 **Read and write permissions**。

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
├── print.html              打印页：排版打印工具（脚本回写兜底）
├── cards.csv               卡牌数据真源
├── cards.json              由 cards.csv 生成，供打印页读取
├── update.command          macOS 双击运行 update.py
├── README.md
├── LICENSE.md              CC BY-NC 4.0
├── docs/
│   ├── rules.md            规则真源（首页规则区由它生成，含初版卡牌留档）
│   ├── map-tiles.md        地图格子数据
│   ├── csv-fields.md       cards.csv 每列的填法与对应 JSON 字段
│   ├── original-cards.md   原版实体卡文字转录
│   ├── original-manual.md  原版说明书转录
│   └── card-diff.md        新版 vs 原版差异对照
├── cards/                  卡牌历史版本存档 v1–v6.md
├── tools/
│   ├── update.py           一键更新：CSV → JSON + 首页 + 打印页
│   └── md2csv.py           一次性迁移脚本：cards/vN.md → cards.csv
└── .github/workflows/      cards.csv / docs/rules.md 变更时自动重生成
```

`photos/`（原版实体照片 13.8MB）不上传仓库，仅本地保留。
