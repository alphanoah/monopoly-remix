# 大富翁卡牌打印版

自制大富翁「机会 / 命运」卡牌的排版打印页。打开页面选好纸张和版式，直接打印即可。

- **在线地址**：开启 Pages 后为 `https://<用户名>.github.io/<仓库名>/`
- **本地使用**：直接双击 `index.html`（此时用内置兜底数据，功能完整）
- **规则**：见 [docs/rules.md](docs/rules.md)；完整地图格子数据见 [docs/map-tiles.md](docs/map-tiles.md)
- **许可**：CC BY-NC 4.0，见 [LICENSE.md](LICENSE.md)

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
- 改完保存 → push，GitHub Actions 会自动重新生成 `cards.json` 并同步页面里的兜底数据。

### 手动生成（可选）

Actions 没跑或想先看结果时，本地跑同一个脚本：

```bash
python3 tools/csv2json.py
```

它会做一次校验（版本、张数、必填字段），通过才写文件，然后：

1. 生成 `cards.json`（全版本，供页面读取）
2. 替换 `index.html` 里 `FALLBACK:START / FALLBACK:END` 之间的内置兜底数据

---

## 为什么有两份数据

| 打开方式 | 数据来源 |
|---|---|
| 线上 Pages | `fetch('cards.json')`，全版本可切换 |
| 本地双击 `index.html` | `file://` 协议下 fetch 会被浏览器拦截 → 回退内置兜底数据 |

内置兜底由脚本从 CSV 自动生成，两份永远一致。页面先用兜底数据立刻渲染（不等网络），JSON 到货后再换掉，所以线上不会白屏。

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
├── index.html              打印页（单文件，无外部依赖）
├── cards.csv               卡牌数据真源
├── cards.json              由 cards.csv 生成，供页面读取
├── README.md
├── LICENSE.md              CC BY-NC 4.0
├── docs/
│   ├── rules.md            游戏规则（含初版卡牌留档）
│   ├── map-tiles.md        地图格子数据
│   ├── csv-fields.md       cards.csv 每列的填法与对应 JSON 字段
│   ├── original-cards.md   原版实体卡文字转录
│   ├── original-manual.md  原版说明书转录
│   └── card-diff.md        新版 vs 原版差异对照
├── cards/                  卡牌历史版本存档 v1–v6.md
├── tools/
│   ├── md2csv.py           一次性迁移脚本：cards/vN.md → cards.csv
│   └── csv2json.py         cards.csv → cards.json + 回写内置兜底
└── .github/workflows/      cards.csv 变更时自动生成 cards.json
```

`photos/`（原版实体照片 13.8MB）不上传仓库，仅本地保留。
