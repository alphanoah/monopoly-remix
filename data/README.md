# data · 脚本生成目录，请勿手改

本目录由 `tools/update.py` 生成。改 `content/` 下的真源后重跑脚本即可：

```bash
python3 tools/update.py        # 或双击 update.command
```

| 文件 | 由谁生成 | 谁在读 |
|---|---|---|
| `cards.json` | `content/cards.csv` | `print.html`（线上 fetch，读不到时用页内兜底） |
| `props.json` | `content/props.md` | `print.html`（线上 fetch，读不到时用页内兜底） |

要改内容请改 `content/` 里的源文件，不要改这里——下次跑脚本会被整块覆盖。
