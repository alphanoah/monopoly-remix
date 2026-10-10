#!/usr/bin/env python3
# cards.csv → cards.json，并把默认版本的卡牌回写进 index.html 的内置兜底数据块
#
# 用法：python3 tools/csv2json.py
# 本地改完 CSV 手动跑一次；push 之后 GitHub Actions 会跑同一个脚本
#
# 输出：
#   1. cards.json        全部版本，供页面 fetch（GitHub Pages 同源可读）
#   2. index.html        替换 /* FALLBACK:START */ ... /* FALLBACK:END */ 之间的内置数据
#                        （本地双击打开是 file:// 协议，fetch 会被 CORS 拦掉，靠它兜底）
import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, 'cards.csv')
JSON_PATH = os.path.join(ROOT, 'cards.json')
HTML_PATH = os.path.join(ROOT, 'index.html')

DEFAULT_VERSION = 'v6'
VERSION_LABELS = {
    'v4': 'v4 · 主线常规版',
    'v5': 'v5 · 邪恶版 · 魔幻',
    'v6': 'v6 · 邪恶版 · 世界之旅',
}
KEEP = ['deck', 'face', 'event', 'effect', 'cond', 'win', 'lose', 'rate']


def load_rows():
    with open(CSV_PATH, encoding='utf-8-sig', newline='') as f:
        return [r for r in csv.DictReader(f)]


def validate(rows):
    errs = []
    seen = {}
    for i, r in enumerate(rows, start=2):  # 表头占第 1 行
        v = (r.get('version') or '').strip()
        deck = (r.get('deck') or '').strip()
        where = '第 %d 行(%s %s #%s)' % (i, v, deck, r.get('seq', '?'))
        if not v:
            errs.append(where + '缺少 version')
        if deck not in ('chance', 'fate'):
            errs.append(where + 'deck 必须是 chance 或 fate')
            continue
        if not (r.get('event') or '').strip():
            errs.append(where + 'event 不能为空')
        if deck == 'chance':
            if (r.get('face') or '').strip() not in ('smile', 'frown'):
                errs.append(where + '机会牌 face 必须是 smile 或 frown')
            if not (r.get('effect') or '').strip():
                errs.append(where + '机会牌 effect 不能为空')
        else:
            for k in ('cond', 'win', 'lose'):
                if not (r.get(k) or '').strip():
                    errs.append(where + '命运牌 %s 不能为空' % k)
        seen.setdefault(v, {'chance': 0, 'fate': 0})
        if (r.get('use') or '1').strip() == '1':
            seen[v][deck] += 1
    for v, c in seen.items():
        print('  %s：机会 %d 张 / 命运 %d 张' % (v, c['chance'], c['fate']))
    return errs


def build(rows):
    versions = {}
    for r in rows:
        if (r.get('use') or '1').strip() != '1':
            continue
        v = (r.get('version') or '').strip()
        versions.setdefault(v, [])
        item = {}
        for k in KEEP:
            val = (r.get(k) or '').strip()
            if val:
                item[k] = val
        versions[v].append(item)

    order = []
    for r in rows:
        v = (r.get('version') or '').strip()
        if v and v not in order:
            order.append(v)

    out = {
        'default': DEFAULT_VERSION if DEFAULT_VERSION in versions else (order[-1] if order else ''),
        'order': order,
        'versions': {
            v: {
                'label': VERSION_LABELS.get(v, v.upper()),
                'cards': versions[v],
            } for v in order
        },
    }
    return out


def write_html_fallback(data):
    if not os.path.exists(HTML_PATH):
        print('  跳过：未找到 %s' % HTML_PATH)
        return
    vid = data['default']
    cards = data['versions'][vid]['cards']
    js = 'const FALLBACK = ' + json.dumps(
        {'version': vid, 'label': data['versions'][vid]['label'], 'cards': cards},
        ensure_ascii=False, indent=2).replace('\n', '\n  ') + ';'

    with open(HTML_PATH, encoding='utf-8') as f:
        html = f.read()
    block = '  /* FALLBACK:START */  // 由 tools/csv2json.py 生成，请勿手改\n' \
            '  %s\n' \
            '  /* FALLBACK:END */' % js
    new, n = re.subn(
        r'[ \t]*\/\* FALLBACK:START \*\/.*?\/\* FALLBACK:END \*\/',
        lambda m: block, html, flags=re.S)
    if n != 1:
        print('  !! index.html 里没找到唯一的 FALLBACK 标记块，已跳过回写')
        return
    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(new)
    print('  已回写 index.html 内置兜底数据（%s，%d 张）' % (vid, len(cards)))


def main():
    print('读取 %s' % CSV_PATH)
    rows = load_rows()
    errs = validate(rows)
    if errs:
        print('\n校验未通过，未生成任何文件：')
        for e in errs:
            print('  - ' + e)
        sys.exit(1)
    data = build(rows)
    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('已写入 %s（%d 个版本，默认 %s）' % (JSON_PATH, len(data['versions']), data['default']))
    write_html_fallback(data)


if __name__ == '__main__':
    main()
