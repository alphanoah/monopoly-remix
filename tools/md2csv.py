#!/usr/bin/env python3
# 一次性迁移脚本：把 cards/vN.md 里的表格抽成 cards.csv
# 用法：python3 tools/md2csv.py
# 生成后请人工核对 cards.csv，确认无误再提交（之后就以 CSV 为准，不再回头改 md）
import csv
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, 'cards')
OUT = os.path.join(ROOT, 'cards.csv')

VERSIONS = ['v4', 'v5', 'v6']
FIELDS = ['version', 'deck', 'seq', 'face', 'event', 'effect', 'cond', 'win', 'lose', 'rate', 'use']


def clean(s):
    s = s.strip()
    s = re.sub(r'\*\*(.+?)\*\*', r'\1', s)   # 去掉 markdown 粗体
    s = s.replace('`', '')
    return s.strip()


def split_row(line):
    line = line.strip()
    if not line.startswith('|'):
        return None
    cells = [clean(c) for c in line.strip('|').split('|')]
    return cells


def parse_md(path, version):
    rows = []
    deck = None
    with open(path, encoding='utf-8') as f:
        for line in f:
            if line.startswith('## '):
                head = line[3:].strip()
                if head.startswith('机会牌'):
                    deck = 'chance'
                elif head.startswith('命运牌'):
                    deck = 'fate'
                else:
                    deck = None
                continue
            if deck is None:
                continue
            cells = split_row(line)
            if not cells:
                continue
            # 表头行 / 分隔行
            if cells[0] in ('#', '') or set(''.join(cells)) <= set('-: '):
                continue
            if not re.fullmatch(r'\d+', cells[0]):
                continue
            seq = int(cells[0])
            # 机会牌表 3 列、命运牌表 6 列；列数不符的是夹在中间的「零期望校验表」等，跳过
            if deck == 'chance' and len(cells) != 3:
                continue
            if deck == 'fate' and len(cells) != 6:
                continue
            row = {k: '' for k in FIELDS}
            row['version'] = version
            row['deck'] = deck
            row['seq'] = seq
            if deck == 'chance':
                row['face'] = 'smile' if seq <= 14 else 'frown'
                row['event'] = cells[1]
                row['effect'] = cells[2]
            else:
                row['event'] = cells[1]
                row['cond'] = cells[2]
                row['rate'] = cells[3]
                row['win'] = cells[4]
                row['lose'] = cells[5]
            row['use'] = '1'
            rows.append(row)
    return rows


def main():
    all_rows = []
    for v in VERSIONS:
        p = os.path.join(SRC_DIR, v + '.md')
        rows = parse_md(p, v)
        ch = sum(1 for r in rows if r['deck'] == 'chance')
        fa = sum(1 for r in rows if r['deck'] == 'fate')
        print('%s: 机会 %d 张 / 命运 %d 张' % (v, ch, fa))
        if ch != 20 or fa != 20:
            print('  !! 张数不对，请检查表格结构')
        all_rows += rows

    with open(OUT, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(all_rows)
    print('已写入 %s，共 %d 行' % (OUT, len(all_rows)))


if __name__ == '__main__':
    main()
