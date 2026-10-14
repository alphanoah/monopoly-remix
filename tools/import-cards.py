#!/usr/bin/env python3
# 卡牌 CSV → source/cards.md 回导脚本。
#
#   python3 tools/import-cards.py ~/Downloads/cards.csv      # 校验 + 写回 source/cards.md
#   python3 tools/import-cards.py ~/Downloads/cards.csv -n   # 只校验预览，不写文件
#
# 什么时候用：在首页「机会/命运卡牌」区点「导出 CSV / Excel」，用电子表格批量改完之后，
# 把 CSV 写回 md 真源（cards.md 才是受版本控制的真源，CSV 只是编辑的中转格式）。
#
# CSV 列必须是：version,deck,seq,face,event,effect,cond,win,lose,rate,use
# （首页导出的就是这个格式）。版本名沿用现有 cards.md 的 ## 小节标题，新版本默认显示版本号大写。
# 写回前会把生成的 md 再解析一遍，和 CSV 直接构建的结果逐字段比对，不一致就不写文件。
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import cards, paths  # 解析 / 校验 / 生成用的都是构建链同一套函数，保证不漂移

REQUIRED_COLS = ['version', 'deck', 'seq', 'face', 'event', 'effect', 'cond', 'win', 'lose', 'rate', 'use']

# 首次从 cards.csv 迁移时用的版本名（之后以 cards.md 的 ## 标题为准，这里只是兜底）
LEGACY_LABELS = {
    'v4': 'v4 · 主线常规版',
    'v5': 'v5 · 邪恶版 · 魔幻',
    'v6': 'v6 · 邪恶版 · 世界之旅',
    'v7': 'v7 · 邪恶版 · 世界之旅（修订）',
}


def main():
    ap = argparse.ArgumentParser(description='卡牌 CSV → source/cards.md 回导')
    ap.add_argument('csv_path', help='首页导出 / Excel 编辑后的 CSV 文件')
    ap.add_argument('-n', '--dry-run', action='store_true', help='只校验和预览，不写文件')
    args = ap.parse_args()

    print('读取 %s' % args.csv_path)
    with open(args.csv_path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_COLS if c not in (reader.fieldnames or [])]
        if missing:
            print('CSV 缺列：%s\n需要的表头：%s' % ('、'.join(missing), ','.join(REQUIRED_COLS)))
            sys.exit(1)
        rows = list(reader)
    if not rows:
        print('CSV 里一行数据都没有')
        sys.exit(1)

    rows = cards.fix_plus(rows)
    errs = cards.validate(rows)
    if errs:
        print('\n校验未通过，未改动任何文件：')
        for e in errs:
            print('  - ' + e)
        sys.exit(1)

    # 版本名：沿用现有 cards.md 的 ## 标题；没有就退内置旧版名 / 版本号大写
    labels = {}
    if os.path.exists(paths.CARDS_MD_PATH):
        with open(paths.CARDS_MD_PATH, encoding='utf-8') as f:
            _, labels, _ = cards.parse_cards_md(f.read())
    versions = []
    for r in rows:
        v = (r.get('version') or '').strip()
        if v and v not in versions:
            versions.append(v)
    for v in versions:
        labels.setdefault(v, LEGACY_LABELS.get(v, v.upper()))
    new_versions = [v for v in versions if v not in LEGACY_LABELS and labels[v] == v.upper()]
    if new_versions:
        print('  新版本 %s 暂无中文名，先显示版本号；可在 cards.md 的 ## 标题里补' % '、'.join(new_versions))

    md = cards.cards_to_md(rows, labels)

    # 回读校验：生成的 md 再解析一次，必须和 CSV 直接构建的结果一致，否则不写
    rows2, labels2, errs2 = cards.parse_cards_md(md)
    if errs2 or cards.build(rows2, labels2) != cards.build(rows, labels):
        print('!! 回读校验失败：生成的 md 与 CSV 数据不一致，未写文件')
        for e in errs2:
            print('  - ' + e)
        sys.exit(1)

    if args.dry_run:
        print('\n' + md)
        print('（--dry-run）未写文件')
        return
    with open(paths.CARDS_MD_PATH, 'w', encoding='utf-8') as f:
        f.write(md)
    used = sum(1 for r in rows if (r.get('use') or '1').strip() == '1')
    print('已写回 %s（%d 个版本，%d / %d 张启用）' % (paths.CARDS_MD_PATH, len(versions), used, len(rows)))
    print('再跑 python3 tools/build.py 同步到页面。')


if __name__ == '__main__':
    main()
