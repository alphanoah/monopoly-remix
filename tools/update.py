#!/usr/bin/env python3
# 一键更新：content/cards.csv → data/cards.json + index.html（首页）+ print.html（打印页）
#
#   python3 tools/update.py
#
# 做四件事：
#   1. 校验 content/cards.csv（结构、必填字段、每版本张数）
#   2. 生成 data/cards.json                 —— 打印页线上 fetch 用
#   3. 重写 index.html 的卡牌数据、规则三版切换区、道具清单 —— 首页内容（静态，离线可看）
#   4. 回写 print.html 的内置兜底数据         —— 本地 file:// 打开时用
#   5. 重写 original.html 的原版资料区        —— 原版资料页
#
# 校验不通过就不写任何文件。GitHub Actions 跑的是同一个脚本。
import collections
import csv
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_DIR = os.path.join(ROOT, 'content')
DATA_DIR = os.path.join(ROOT, 'data')
CSV_PATH = os.path.join(CONTENT_DIR, 'cards.csv')
JSON_PATH = os.path.join(DATA_DIR, 'cards.json')
PROPS_JSON_PATH = os.path.join(DATA_DIR, 'props.json')
INDEX_PATH = os.path.join(ROOT, 'index.html')
PRINT_PATH = os.path.join(ROOT, 'print.html')
PROPS_PATH = os.path.join(CONTENT_DIR, 'props.md')
ORIGINAL_DIR = os.path.join(CONTENT_DIR, 'original')
ORIGINAL_PATH = os.path.join(ROOT, 'original.html')
# 电子地图（三档布局：加厚环/原版/打印版）：真源 JSON → map-print-svg.html 的内置兜底块
MAP_DATA_PATH = os.path.join(CONTENT_DIR, 'map-print-data.json')
MAP_SVG_PRINT_PATH = os.path.join(ROOT, 'map-print-svg.html')  # 电子地图（打印版数据）
READMED_PATH = os.path.join(ROOT, 'README.md')
MAP_DATA = None        # main() 读好的棋盘数据，资料页的表格生成器从这里取


def title_for_cards(text):
    """原版卡牌区块标题：张数按 md 表格的实际行数算（改了表格，标题自动跟着变）。"""
    fate = chance = 0
    sec = ''
    for line in text.split('\n'):
        if line.startswith('## '):
            sec = line[3:].strip()
            continue
        if not line.startswith('|') or '---' in line or line.startswith('| 编号'):
            continue
        if sec.startswith('命运牌'):
            fate += 1
        elif sec.startswith('机会牌'):
            chance += 1
    if not (fate or chance):
        return '原版命运牌 & 机会牌'
    return '原版命运牌 & 机会牌（%d + %d 张）' % (fate, chance)


def title_for_tiles(text):
    """原版地图区块标题：格数与颜色组数由棋盘 JSON 现算（没有数据时回退到 md 的概览表）。"""
    if MAP_DATA:
        s = map_summary(MAP_DATA)
        return '原版地图格子数据（%d 格 · %d 个颜色组）' % (s['total'], s['groups'])
    found = {}
    for line in text.split('\n'):
        if not line.startswith('|') or '---' in line:
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        if len(cells) == 2 and cells[0] in ('总格数', '颜色组数'):
            found[cells[0]] = cells[1]
    n = re.match(r'\d+', found.get('总格数', ''))
    g = re.match(r'\d+', found.get('颜色组数', ''))
    if n and g:
        return '原版地图格子数据（%s 格 · %s 个颜色组）' % (n.group(), g.group())
    return '原版地图格子数据'


# 原版实体资料：文件名 → 页面上的区块标题（None = 直接用 md 里的一级标题；函数 = 从 md 内容现算）
#       → 是否默认展开
#   标题里的张数 / 格数不写死：改了 md 表格，区块标题自动跟着变
ORIGINAL_DOCS = [
    ('cards.md', title_for_cards, True),
    ('manual.md', None, True),
    ('map-data-guide.md', '地图数据使用指南（速览 · 投资建议 · FAQ）', False),
    ('map-tiles.md', title_for_tiles, False),
]

# 首页「游戏规则」区：三版并列，点卡片切换
#   (key, 卡片主标题, 卡片副标题, md 路径, 页面里的源文件链接, 链接前缀, 要折叠的小节)
#   折叠小节 = (标题层级, 标题关键字, 是否折到文末, 折叠后显示的标题 / None = 用原标题)
RULE_DOCS = [
    ('original', '原版', '实体说明书',
     os.path.join(ORIGINAL_DIR, 'manual.md'), 'content/original/manual.md',
     'content/original/', []),
    ('v1', 'v1', '初版改版规则',
     os.path.join(CONTENT_DIR, 'rules.md'), 'content/rules.md', 'content/',
     [(3, '卡牌', True, '卡牌（cards.csv 与历史存档）'),
      (4, '备选', False, None)]),
    ('v2', 'v2', '最新改版规则',
     os.path.join(CONTENT_DIR, 'new-rule.md'), 'content/new-rule.md', 'content/', []),
]
DEFAULT_RULE = 'v2'

DEFAULT_VERSION = 'v7'
VERSION_LABELS = {
    'v4': 'v4 · 主线常规版',
    'v5': 'v5 · 邪恶版 · 魔幻',
    'v6': 'v6 · 邪恶版 · 世界之旅',
    'v7': 'v7 · 邪恶版 · 世界之旅（修订）',
}
KEEP = ['deck', 'face', 'event', 'effect', 'cond', 'win', 'lose', 'rate']
# 金额字段：Excel / Numbers 存 CSV 时会把「+3000」当数值，正号被丢掉，这里补回来
AMOUNT_FIELDS = ('effect', 'win', 'lose')


# ---------- CSV 读取与校验 ----------
def load_rows():
    with open(CSV_PATH, encoding='utf-8-sig', newline='') as f:
        return [r for r in csv.DictReader(f)]


def fix_plus(rows):
    """金额写成纯数字时补回正号（电子表格存 CSV 会丢掉 +）。

    只处理「整个格子就是一个正整数」的情况，含文字的（如「+2000，被举报者…」）
    电子表格会当文本保留，负数也不受影响。
    """
    n = 0
    for r in rows:
        for k in AMOUNT_FIELDS:
            v = (r.get(k) or '').strip()
            if re.fullmatch(r'\d+', v) and int(v) > 0:
                r[k] = '+' + v
                n += 1
    if n:
        print('  补回 %d 个金额的正号（电子表格存 CSV 会丢 +，脚本自动修复）' % n)
    return rows


def validate(rows):
    errs = []
    count = {}
    for i, r in enumerate(rows, start=2):
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
        if (r.get('use') or '1').strip() == '1':
            count.setdefault(v, {'chance': 0, 'fate': 0})[deck] += 1
    for v, c in count.items():
        print('  %s：机会 %d 张 / 命运 %d 张' % (v, c['chance'], c['fate']))
    return errs


def build(rows):
    versions, order = {}, []
    for r in rows:
        v = (r.get('version') or '').strip()
        if v and v not in order:
            order.append(v)
        if (r.get('use') or '1').strip() != '1':
            continue
        item = {}
        for k in KEEP:
            val = (r.get(k) or '').strip()
            if val:
                item[k] = val
        versions.setdefault(v, []).append(item)
    return {
        'default': DEFAULT_VERSION if DEFAULT_VERSION in versions else (order[-1] if order else ''),
        'order': order,
        'versions': {
            v: {'label': VERSION_LABELS.get(v, v.upper()), 'cards': versions[v]} for v in order
        },
    }


# ---------- 简易 markdown → HTML（够三版规则文档用：标题/列表/引用/表格/链接/粗体/行内码）----------
def norm_href(p):
    """把 md 里「相对自身目录」的链接折叠成相对站点根的路径：content/../docs/x → docs/x。"""
    parts = []
    for seg in p.split('/'):
        if seg == '..':
            if parts:
                parts.pop()
        elif seg and seg != '.':
            parts.append(seg)
    return '/'.join(parts)


def inline(t, prefix='content/'):
    t = html.escape(t)
    t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'`(.+?)`', r'<code>\1</code>', t)
    t = re.sub(r'\[(.+?)\]\((?!https?:|#)(.+?)\)',
               lambda m: '<a href="%s">%s</a>' % (norm_href(prefix + m.group(2)), m.group(1)), t)
    t = re.sub(r'\[(.+?)\]\((https?:.+?)\)', r'<a href="\2">\1</a>', t)
    return t


def render_list(items, prefix):
    out, stack = [], []
    for lvl, ordered, text in items:
        tag = 'ol' if ordered else 'ul'
        while stack and stack[-1][0] > lvl:
            out.append('</li></%s>' % stack.pop()[1])
        if not stack:
            out.append('<%s>' % tag)
            stack.append((lvl, tag))
        else:
            top_lvl, top_tag = stack[-1]
            if lvl > top_lvl:
                out.append('<%s>' % tag)
                stack.append((lvl, tag))
            elif top_tag != tag:
                out.append('</li></%s>' % top_tag)
                stack.pop()
                out.append('<%s>' % tag)
                stack.append((lvl, tag))
            else:
                out.append('</li>')
        out.append('<li>' + inline(text, prefix))
    while stack:
        out.append('</li></%s>' % stack.pop()[1])
    return '\n'.join(out)


def render_table(lines, i, prefix):
    """解析 markdown 表格，返回 (html, 下一行下标)。首行必须是表头 + 分隔行。"""
    cells = lambda s: [c.strip() for c in s.strip().strip('|').split('|')]
    head = cells(lines[i])
    i += 2
    rows = []
    while i < len(lines) and lines[i].strip().startswith('|'):
        rows.append(cells(lines[i]))
        i += 1
    out = ['<div class="tw"><table>', '<thead><tr>' +
           ''.join('<th>%s</th>' % inline(c, prefix) for c in head) + '</tr></thead>', '<tbody>']
    for r in rows:
        out.append('<tr>' + ''.join('<td>%s</td>' % inline(c, prefix) for c in r) + '</tr>')
    out.append('</tbody></table></div>')
    return '\n'.join(out), i


def md_to_html(md, prefix='content/'):
    lines = md.replace('\r\n', '\n').split('\n')
    out, i = [], 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        if not line.strip():
            i += 1
            continue
        indent = len(line) - len(line.lstrip())
        s = line.strip()

        # 标题：# 是文件标题，首页已有大标题，跳过
        m = re.match(r'^(#{1,6})\s+(.*)', s)
        if m:
            lvl = len(m.group(1))
            if lvl >= 2:
                out.append('<h%d>%s</h%d>' % (min(lvl + 1, 6), inline(m.group(2), prefix), min(lvl + 1, 6)))
            i += 1
            continue

        # 表格（表头行 + |---| 分隔行）
        if s.startswith('|') and i + 1 < len(lines) and re.match(r'^\|[\s:|-]+\|$', lines[i + 1].strip()):
            tbl, i = render_table(lines, i, prefix)
            out.append(tbl)
            continue

        # 水平分隔线 --- / ***（首页用标题间距就够，直接跳过）
        if re.match(r'^(-{3,}|\*{3,}|_{3,})$', s):
            i += 1
            continue

        # 列表
        if re.match(r'^([-*+]|\d+[.)])\s+', s):
            items = []
            while i < len(lines):
                cur = lines[i].rstrip()
                if not cur.strip():
                    break
                ci = len(cur) - len(cur.lstrip())
                cs = cur.strip()
                mm = re.match(r'^(\d+[.)]|[-*+])\s+(.*)', cs)
                if not mm:
                    break
                items.append((ci // 2, bool(re.match(r'^\d', mm.group(1))), mm.group(2)))
                i += 1
            out.append(render_list(items, prefix))
            continue

        # 引用
        if s.startswith('>'):
            buf = []
            while i < len(lines) and lines[i].strip().startswith('>'):
                buf.append(lines[i].strip().lstrip('>').strip())
                i += 1
            out.append('<blockquote>%s</blockquote>' % '<br>'.join(inline(x, prefix) for x in buf))
            continue

        # 普通段落（连续行合并）
        buf = []
        while i < len(lines):
            cur = lines[i].rstrip()
            cs = cur.strip()
            if not cs or re.match(r'^(#{1,6})\s+', cs) or re.match(r'^([-*+]|\d+[.)])\s+', cs) or cs.startswith('>'):
                break
            buf.append(cs)
            i += 1
        if buf:
            out.append('<p>%s</p>' % '<br>'.join(inline(x, prefix) for x in buf))
    return '\n'.join(out)


def md_title(md):
    """取 md 的一级标题，没有就返回空字符串。"""
    m = re.search(r'^#\s+(.+?)\s*$', md, re.M)
    return m.group(1).strip() if m else ''


def build_props():
    """把 content/props.md 转成首页「道具清单」区的内容。"""
    if not os.path.exists(PROPS_PATH):
        print('  跳过：未找到 content/props.md')
        return ''
    with open(PROPS_PATH, encoding='utf-8') as f:
        return md_to_html(f.read())


def parse_props():
    """从 content/props.md 里抽出结构化道具数据：使用规则 + 道具列表（用于打印页）。

    真源仍然是 content/props.md（首页道具清单也由它生成），这里只是把 md 里的表格和
    编号列表读成 dict，给打印页做道具卡用。改道具请改 content/props.md，别改 data/props.json。
    """
    if not os.path.exists(PROPS_PATH):
        print('  跳过：未找到 content/props.md')
        return None
    rules, items, section = [], [], None
    with open(PROPS_PATH, encoding='utf-8') as f:
        for raw in f:
            line = raw.strip()
            if line.startswith('## '):
                section = line[3:].strip()
                continue
            if section == '使用规则':
                m = re.match(r'^\d+\.\s+(.+)$', line)
                if m:
                    rules.append(m.group(1).strip())
            elif section == '道具列表':
                if not line.startswith('|') or '---' in line:
                    continue
                cells = [c.strip() for c in line.strip('|').split('|')]
                if len(cells) < 4 or not cells[0] or cells[0] == '道具':
                    continue
                items.append({'name': cells[0], 'price': cells[1],
                              'effect': cells[2], 'qty': cells[3]})
    if not items:
        print('  跳过：content/props.md 里没解析到道具表格')
        return None
    return {'rules': rules, 'items': items}


def write_props(props):
    if not props:
        return
    with open(PROPS_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(props, f, ensure_ascii=False, indent=2)
        f.write('\n')
    js = ('const PROPS_FALLBACK = ' +
          json.dumps(props, ensure_ascii=False, indent=2).replace('<', '\\u003c') + ';')
    block = ('  /* PROPS:START */  // 由 tools/update.py 从 content/props.md 生成，请勿手改\n'
             '  %s\n'
             '  /* PROPS:END */' % js)
    if swap(PRINT_PATH, r'[ \t]*\/\* PROPS:START \*\/.*?\/\* PROPS:END \*\/', block, '道具兜底数据'):
        print('  props.json + print.html 内置道具兜底（%d 件道具，%d 条规则）'
              % (len(props['items']), len(props['rules'])))


def build_original():
    """把 content/original/ 下的原版实体资料转成 original.html 的正文区块。

    /md 里可以写 `{{STATS:xxx}}` 占位符，渲染时换成从 content/map-print-data.json
    遍历出来的表格——地图那两篇的统计就不再是手抄的。
    """
    parts = []
    for fn, label, opened in ORIGINAL_DOCS:
        path = os.path.join(ORIGINAL_DIR, fn)
        if not os.path.exists(path):
            print('  跳过：未找到 content/original/%s' % fn)
            continue
        with open(path, encoding='utf-8') as f:
            text = f.read()
        if callable(label):                    # 给了个函数 = 按 md 内容现算的标题（张数/格数不写死）
            label = label(text)
        elif label is None:                    # 没写标题就跟 md 的一级标题走
            label = md_title(text) or fn
        body = md_to_html(text, prefix='content/original/')
        body = render_map_stats(body)
        parts.append('<details class="blk"%s><summary><h2>%s</h2><span class="tog"></span></summary>\n'
                     '<div class="md">\n%s\n</div>\n</details>'
                     % (' open' if opened else '', html.escape(label), body))
    return '\n'.join(parts)


# ---------- 地图资料页的表格：全部从 map-print-data.json 遍历出来 ----------
# md 里写 {{STATS:key}}，下面的生成器负责把它换成一张现算的表；改数据改 JSON，跑一次脚本就同步。
SIDE_CN = {'bottom': '底行', 'left': '左行', 'top': '顶行', 'right': '右行'}
EDGES = [('bottom', 0, 16), ('left', 16, 32), ('top', 32, 48), ('right', 48, 0)]   # 四条边：起点角 → 终点角


def md_table(head, rows):
    """生成跟 md_to_html 同款结构的表格（外层 .tw 负责窄屏幕横向滚动）。"""
    out = ['<div class="tw"><table>',
           '<thead><tr>' + ''.join('<th>%s</th>' % h for h in head) + '</tr></thead>', '<tbody>']
    for r in rows:
        out.append('<tr>' + ''.join('<td>%s</td>' % html.escape(str(c)) for c in r) + '</tr>')
    out.append('</tbody></table></div>')
    return '\n'.join(out)


def money(n):
    return '$%s' % format(int(n), ',')


def type_counts(data):
    return collections.Counter((t.get('type') or 'property') for t in data['tiles'])


def group_members(data, gid):
    return sorted([t for t in data['tiles'] if t.get('colorId') == gid], key=lambda t: t['id'])


def segments(ids):
    """连续段数：同组的格子在轨道上被别的格子切成几段（1 段 = 全都挨着）。"""
    n, prev = 0, None
    for i in ids:
        if prev is None or i != prev + 1:
            n += 1
        prev = i
    return n


def property_tiles(data):
    return [t for t in data['tiles'] if (t.get('type') or 'property') == 'property' and t.get('price')]


def edge_ends(data, side):
    """一条边两端的角格名字（编号就是行进顺序，四个角天然排在 0/16/32/48）。"""
    order = sorted([t for t in data['tiles'] if t.get('type') == 'corner'], key=lambda t: t['id'])
    a, b = {'bottom': (0, 1), 'left': (1, 2), 'top': (2, 3), 'right': (3, 0)}[side]
    return order[a]['name'], order[b]['name']


def tile_position(t, start_name, end_name):
    """格子落在边上的哪个位置；只有贴着角落时才额外标注，其余只写「X行」。"""
    side = t.get('side')
    i = None
    if side == 'bottom':
        i = 16 - t['col']
    elif side == 'left':
        i = 16 - t['row']
    elif side == 'top':
        i = t['col']
    elif side == 'right':
        i = t['row']
    if i is None:
        return ''
    label = SIDE_CN[side]
    if i <= 2:
        return '%s（%s后第 %d 格）' % (label, start_name, i)
    if 16 - i <= 2:
        return '%s（%s前第 %d 格）' % (label, end_name, 16 - i)
    return label


def edge_tiles(by_id, a, b):
    n = len(by_id)
    ids = list(range(a, b + 1)) if b > a else list(range(a, n)) + [0]
    return [by_id[i] for i in ids]


def band_label(t, data, gkey):
    if t.get('colorId') and t['colorId'] in gkey:
        return gkey[t['colorId']]['name']
    return {'corner': '角', 'ocean': '海洋'}.get(t.get('type'), '特殊')


def stats_type_table(data):
    counts = type_counts(data)
    rows = []
    for k, meta in data['tileTypes'].items():
        rows.append([meta['name'], counts.get(k, 0), meta.get('desc', '')])
    return md_table(['类型', '数量', '说明'], rows)


def stats_overview(data):
    counts = type_counts(data)
    rows = [['总格数', len(data['tiles'])], ['地产格', '%d 个' % counts.get('property', 0)]]
    for k, meta in data['tileTypes'].items():
        if k == 'property':
            continue
        members = [t['name'] for t in data['tiles'] if (t.get('type') or 'property') == k]
        cell = '%d 个' % len(members)
        if len(set(members)) > 1:                       # 成员各有名字才列举（机会/命运全同名就不列）
            cell += '（%s）' % '、'.join(members)
        rows.append(['%s %s' % (meta['name'], meta.get('nameEn', '').upper()), cell])
    props = property_tiles(data)
    prices = [t['price'] for t in props]
    lo, hi = min(prices), max(prices)
    lo_names = '、'.join(t['name'] for t in props if t['price'] == lo)
    hi_names = '、'.join(t['name'] for t in props if t['price'] == hi)
    s = map_summary(data)
    rows += [['起点酬金', money(data['board'].get('goBonus', 2000))],
             ['总地价', money(sum(prices))],
             ['均价', money(s['avg'])],
             ['最高价', '%s（%s）' % (money(hi), hi_names)],
             ['最低价', '%s（%s）' % (money(lo), lo_names)]]
    return md_table(['项目', '数值'], rows)


def stats_groups(data):
    out = []
    for g in data['colorGroups']:
        ms = group_members(data, g['id'])
        prices = [t['price'] for t in ms]
        avg = int(round(sum(prices) / len(prices)))
        seg = segments([t['id'] for t in ms])
        out.append('<h4>%s %s组（%d 格）</h4>' % (g.get('icon', ''), g['name'], len(ms)))
        out.append('<p>均价 <strong>%s</strong> · 价格区间 %s ~ %s</p>'
                   % (money(avg), money(min(prices)), money(max(prices))))
        rows = []
        for t in ms:
            start, end = edge_ends(data, t['side'])
            rows.append([t['id'], t['name'], t.get('capital', '—'),
                         money(t['price']), tile_position(t, start, end)])
        out.append(md_table(['格号', '国家', '首都', '价格', '位置'], rows))
        out.append('<blockquote>💡 这 %d 格在轨道上被切成 %d 段%s。</blockquote>'
                   % (len(ms), seg, '，段数越多越难集齐' if seg > 1 else '（全部连在一起）'))
    return '\n'.join(out)


def stats_group_rank(data):
    info = []
    for g in data['colorGroups']:
        ms = group_members(data, g['id'])
        prices = [t['price'] for t in ms]
        info.append((int(round(sum(prices) / len(prices))), g, len(ms),
                     min(prices), max(prices), segments([t['id'] for t in ms])))
    info.sort(key=lambda x: -x[0])
    rows = [[i, '%s %s' % (g.get('icon', ''), g['name']), n, money(avg),
             '%s ~ %s' % (money(mn), money(mx)), '%d 段' % seg]
            for i, (avg, g, n, mn, mx, seg) in enumerate(info, 1)]
    return md_table(['排序', '颜色', '格数', '均价', '价格区间', '连续段数'], rows)


def stats_price_dist(data):
    buckets = collections.OrderedDict()
    for t in sorted(property_tiles(data), key=lambda x: -x['price']):
        buckets.setdefault(t['price'], []).append(t['name'])
    return md_table(['价格', '数量', '国家'],
                    [[money(p), len(v), '、'.join(v)] for p, v in buckets.items()])


def stats_key_numbers(data):
    props = property_tiles(data)
    prices = sorted(t['price'] for t in props)
    median = prices[len(prices) // 2]
    lo, hi = prices[0], prices[-1]
    names_at = lambda p: '、'.join(t['name'] for t in props if t['price'] == p)
    go = data['board'].get('goBonus', 2000)
    items = [
        '地产格 <strong>%d</strong> 个；总地价 <strong>%s</strong>；均价 <strong>%s</strong>；中位数 <strong>%s</strong>'
        % (len(prices), money(sum(prices)), money(int(round(sum(prices) / len(prices)))), money(median)),
        '最贵：<strong>%s %s</strong>（%s）' % (names_at(hi), money(hi),
                                        '全盘唯一' if prices.count(hi) == 1 else '共 %d 个' % prices.count(hi)),
        '最便宜 <strong>%s</strong>（%d 个）：%s' % (money(lo), prices.count(lo), names_at(lo)),
        '最高 : 最低 = %d : %d ≈ <strong>%.2f : 1</strong>' % (hi, lo, hi / float(lo)),
    ]
    if hi:
        items.append('起点酬金 %s %s最贵地价的一半' % (money(go), '正好是' if go * 2 == hi else '约为'))
    if all(p % 100 == 0 for p in prices):
        items.append('所有价格均为 $100 的整数倍')
    return '<ul>' + ''.join('<li>%s</li>' % x for x in items) + '</ul>'


def stats_corners(data):
    by_id = {t['id']: t for t in data['tiles']}
    n = len(by_id)
    rows = []
    for c in sorted([t for t in data['tiles'] if t.get('type') == 'corner'], key=lambda t: t['id']):
        lft, rgt = by_id[(c['id'] - 1) % n], by_id[(c['id'] + 1) % n]
        lp, rp = lft.get('price') or 0, rgt.get('price') or 0
        if lp == rp:
            judge = '对称高价 ✨'
        elif abs(lp - rp) <= 400:
            judge = '接近对称'
        else:
            judge = '不对称（落差 %s）' % money(abs(lp - rp))
        rows.append(['%s（#%d）' % (c['name'], c['id']),
                     '%s %s' % (lft['name'], money(lp)),
                     '%s %s' % (rgt['name'], money(rp)),
                     judge])
    return md_table(['角', '左侧', '右侧', '对称性'], rows)


def stats_track(data):
    by_id = {t['id']: t for t in data['tiles']}
    gkey = {g['id']: g for g in data['colorGroups']}
    out = []
    for side, a, b in EDGES:
        ts = edge_tiles(by_id, a, b)
        out.append('<h4>%s（%s → %s）</h4>' % (SIDE_CN[side], ts[0]['name'], ts[-1]['name']))
        out.append('<p>按行进顺序排列，两端的角落各出现一次。</p>')
        rows = []
        for t in ts:
            name = t['name'] + '（起点）' if t['id'] == 0 and t.get('type') == 'corner' else t['name']
            if t.get('price'):
                price = money(t['price'])
            elif t['id'] == 0:
                price = '得酬金 %s' % money(data['board'].get('goBonus', 2000))
            else:
                price = '—'
            rows.append([t['id'], name, t.get('capital', '—'), price, band_label(t, data, gkey)])
        out.append(md_table(['#', '格子', '首都', '价格', '色带'], rows))
    return '\n'.join(out)


MAP_STATS = collections.OrderedDict([
    ('typeTable', stats_type_table),
    ('overview', stats_overview),
    ('groups', stats_groups),
    ('groupRank', stats_group_rank),
    ('priceDist', stats_price_dist),
    ('keyNumbers', stats_key_numbers),
    ('corners', stats_corners),
    ('track', stats_track),
])


def render_map_stats(body):
    """把 md 里的 {{STATS:key}} 占位符换成从棋盘 JSON 现算的表格（没有数据时给个提示）。"""
    miss = '<p class="empty">棋盘数据没读到：先跑一次 tools/update.py 生成 map-print-data.json 的兜底。</p>'
    for key, fn in MAP_STATS.items():
        marker = '<p>{{STATS:%s}}</p>' % key
        if marker in body:
            body = body.replace(marker, fn(MAP_DATA) if MAP_DATA else miss)
    unknown = sorted(set(re.findall(r'\{\{STATS:([a-zA-Z]+)\}\}', body)))
    if unknown:
        print('  !! 资料 md 里有不认识的统计占位符：%s（可用：%s）'
              % ('、'.join(unknown), '、'.join(MAP_STATS)))
    return body


def strip_tags(s):
    """去掉行内标签，只留文字（折叠标题里常有 <code>【新版新增】</code> 这类标注）。"""
    return html.unescape(re.sub(r'<[^>]+>', '', s)).strip()


def fold(rules_html, level, keyword, to_end=False, title=None):
    """把标题含 keyword 的某一级小节折进 <details>，默认收起（原生折叠，不依赖 JS）。

    to_end=False 时只折到下一个同级/上级标题为止（用于「备选：北极监狱」这类可选小节）。
    """
    out = rules_html
    while True:
        m = re.search(r'<h%d>(.*?%s.*?)</h%d>' % (level, keyword, level), out)
        if not m:
            return out
        end = len(out)
        if not to_end:
            nxt = re.search(r'<h[34][ >]', out[m.end():])
            if nxt:
                end = m.end() + nxt.start()
        summary = title or strip_tags(m.group(1))
        out = ('%s<details class="fold"><summary>%s</summary>\n%s\n</details>\n%s'
               % (out[:m.start()], html.escape(summary), out[m.end():end], out[end:]))


def build_rules():
    """生成首页规则区：原版 / v1 / v2 三版并列，点上方的卡片切换（默认 v2）。"""
    docs = []
    for key, name, desc, path, rel, prefix, folds in RULE_DOCS:
        if not os.path.exists(path):
            print('  跳过：未找到 %s' % rel)
            continue
        with open(path, encoding='utf-8') as f:
            text = f.read()
        body = md_to_html(text, prefix=prefix)
        for level, keyword, to_end, title in folds:
            body = fold(body, level, keyword, to_end, title)
        docs.append({'key': key, 'name': name, 'desc': desc, 'rel': rel,
                     'title': md_title(text) or name, 'body': body})
    if not docs:
        return '<p class="empty">规则文件都没找到，跑一次 <code>python3 tools/update.py</code>。</p>'
    default = DEFAULT_RULE if any(d['key'] == DEFAULT_RULE for d in docs) else docs[-1]['key']

    tabs, panes = [], []
    for d in docs:
        on = d['key'] == default
        tabs.append(
            '<button type="button" class="rtab%s" role="tab" aria-selected="%s" id="rtab-%s" '
            'aria-controls="rview-%s" data-rule="%s"><span class="rttxt">'
            '<span class="rt-n">%s</span><span class="rt-d">%s</span></span>%s</button>'
            % (' on' if on else '', 'true' if on else 'false', d['key'], d['key'], d['key'],
               d['name'], d['desc'], '<span class="rt-b">默认</span>' if on else ''))
        panes.append(
            '<div class="rview%s" role="tabpanel" id="rview-%s" aria-labelledby="rtab-%s" data-rule="%s">\n'
            '<h3 class="rttl">%s</h3>\n<div class="md">\n%s\n</div>\n'
            '<p class="rsrc">源文件 <a href="%s">%s</a></p>\n</div>'
            % (' on' if on else '', d['key'], d['key'], d['key'], html.escape(d['title']),
               d['body'], d['rel'], d['rel']))

    note = ('<p class="rnote">规则改过两轮，这里把三版并列放好，点上面的卡片切换。'
            '<strong>原版</strong> = 实体《大富翁世界之旅（银牌）》说明书的原文，'
            '<strong>v1</strong> = 第一次改版，<strong>v2</strong> = 现在在玩的最新一版。</p>')
    print('  规则三版：%s（默认 %s）' % (' / '.join(d['name'] for d in docs), default))
    return (note + '\n<div class="rtabs" role="tablist" aria-label="规则版本">\n' + '\n'.join(tabs) +
            '\n</div>\n<div class="rviews">\n' + '\n'.join(panes) + '\n</div>')


# ---------- 写入 ----------
def swap(path, pattern, block, label):
    if not os.path.exists(path):
        print('  跳过：未找到 %s' % path)
        return False
    with open(path, encoding='utf-8') as f:
        txt = f.read()
    new, n = re.subn(pattern, lambda m: block, txt, flags=re.S)
    if n != 1:
        print('  !! %s 里的标记块不是唯一（找到 %d 处），已跳过 %s' % (path, n, label))
        return False
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new)
    return True


def write_json(data):
    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('  cards.json（%d 个版本，默认 %s）' % (len(data['versions']), data['default']))


def write_original(original_html):
    if swap(ORIGINAL_PATH,
            r'<!-- ORIGINAL:START -->.*?<!-- ORIGINAL:END -->',
            '<!-- ORIGINAL:START -->\n' + original_html + '\n<!-- ORIGINAL:END -->',
            '原版资料区块'):
        print('  original.html（%d 字符）' % len(original_html))


def write_index(data, rules_html, props_html):
    js = 'const DECKS = ' + json.dumps(data, ensure_ascii=False, indent=2).replace('<', '\\u003c') + ';'
    ok1 = swap(INDEX_PATH,
               r'/\* CARDS:START \*/.*?/\* CARDS:END \*/',
               '/* CARDS:START */\n' + js + '\n/* CARDS:END */',
               '卡牌数据')
    ok2 = swap(INDEX_PATH,
               r'<!-- RULES:START -->.*?<!-- RULES:END -->',
               '<!-- RULES:START -->\n' + rules_html + '\n<!-- RULES:END -->',
               '规则区')
    ok3 = swap(INDEX_PATH,
               r'<!-- PROPS:START -->.*?<!-- PROPS:END -->',
               '<!-- PROPS:START -->\n' + props_html + '\n<!-- PROPS:END -->',
               '道具区')
    if ok1 and ok2 and ok3:
        total = sum(len(data['versions'][v]['cards']) for v in data['order'])
        print('  index.html（%d 个卡牌版本共 %d 张 + 规则三版 %d 字符 + 道具区 %d 字符）'
              % (len(data['order']), total, len(rules_html), len(props_html)))


def write_print_fallback(data):
    vid = data['default']
    cards = data['versions'][vid]['cards']
    js = 'const FALLBACK = ' + json.dumps(
        {'version': vid, 'label': data['versions'][vid]['label'], 'cards': cards},
        ensure_ascii=False, indent=2).replace('<', '\\u003c') + ';'
    block = ('  /* FALLBACK:START */  // 由 tools/update.py 生成，请勿手改\n'
             '  %s\n'
             '  /* FALLBACK:END */' % js)
    if swap(PRINT_PATH, r'[ \t]*\/\* FALLBACK:START \*\/.*?\/\* FALLBACK:END \*\/', block, '兜底数据'):
        print('  print.html 内置兜底（%s，%d 张）' % (vid, len(cards)))


# ---------- 棋盘：统计、校验、注入 ----------
def map_counts(data):
    """按 tileTypes 定义的类型统计格子数，返回 [{'key','name','count'}, ...]（保持 JSON 里的顺序）。"""
    types = data.get('tileTypes') or {}
    counter = collections.Counter((t.get('type') or 'property') for t in data['tiles'])
    out = []
    for k, meta in types.items():
        if counter.get(k):
            out.append({'key': k, 'name': meta.get('name', k), 'count': counter[k]})
    for k, n in counter.items():               # 数据里有、tileTypes 没定义的类型也别漏
        if k not in types:
            out.append({'key': k, 'name': k, 'count': n})
    return out


def map_summary(data):
    """给首页 / README 用的棋盘速览。数字全部从 JSON 现算，不写死。"""
    tiles = data['tiles']
    counts = map_counts(data)
    prices = [t['price'] for t in tiles if t.get('price')]
    avg = int(round(sum(prices) / len(prices))) if prices else 0
    cheapest = min(prices) if prices else 0
    dearest = max(prices) if prices else 0
    board = data.get('board') or {}
    mm = board.get('printMM') or 800
    cm = ('%g' % (mm / 10.0))
    return {
        'total': len(tiles),
        'detail': ' · '.join('%d %s' % (c['count'], c['name']) for c in counts),
        'groups': len(data.get('colorGroups') or []),
        'prices': len(prices),
        'avg': avg,
        'min': cheapest,
        'max': dearest,
        'mm': mm,
        'cm': cm,
    }


def write_map_info(data):
    """首页「电子地图」区的说明文字：格子数、各类格子、颜色组数、成品尺寸全部从 JSON 现算。"""
    s = map_summary(data)
    html_block = (
        '  <p class="meta">电子版「世界之旅」棋盘：<strong>{total}</strong> 格全图'
        '（{detail}，{groups} 个颜色组），地产均价 ${avg:,}。'
        '鼠标拖动平移、滚轮缩放、双击放大，手机上也能单指拖、双指捏合。<br>'
        '要实体棋盘就走打印版：<strong>{cm}×{cm}cm</strong> 见方（{mm}×{mm}mm）、边距无，'
        '正方形棋盘居中，直接 ⌘/Ctrl + P。</p>'
    ).format(**s)
    if swap(INDEX_PATH,
            r'<!-- MAPINFO:START -->.*?<!-- MAPINFO:END -->',
            '<!-- MAPINFO:START -->\n' + html_block + '\n  <!-- MAPINFO:END -->',
            '电子地图区说明'):
        print('  index.html 电子地图区（%d 格 / %d 组 / %scm）' % (s['total'], s['groups'], s['cm']))


def write_readme_stats(data, props, cards):
    """README 的「数据速览」表格：卡牌、道具、棋盘三个来源的数字全部现算，避免文档写死后不同步。"""
    s = map_summary(data)
    versions = cards['order']
    vline = '、'.join(versions)
    detail = []
    for v in versions:
        cs = cards['versions'][v]['cards']
        c = collections.Counter(x['deck'] for x in cs)
        detail.append('%s %d+%d' % (v, c['chance'], c['fate']))
    rows = [
        ('卡牌', '%d 个版本（%s），默认 <code>%s</code><br>%s'
         % (len(versions), vline, cards['default'], ' · '.join(detail))),
        ('道具', '%d 件，使用规则 %d 条' % (len(props['items']), len(props['rules']))),
        ('棋盘格子', '%d 格<br>%s' % (s['total'], s['detail'])),
        ('颜色组', '%d 组' % s['groups']),
        ('地价', '共 %d 块地产，均价 $%s（$%s ~ $%s）'
         % (s['prices'], '{:,}'.format(s['avg']), '{:,}'.format(s['min']), '{:,}'.format(s['max']))),
        ('实物尺寸', '%s×%s cm 软垫（%s×%s mm，2mm 厚 / 3mm 锁边）' % (s['cm'], s['cm'], s['mm'], s['mm'])),
    ]
    body = '\n'.join('| %s | %s |' % (a, b) for a, b in rows)
    table = ('| 项目 | 数量 |\n|------|------|\n' + body)
    note = ('> 这一节由 <code>tools/update.py</code> 从各真源统计后写入，'
            '改了 CSV / md / JSON 跑一次脚本就会同步，**不要手改**。')
    if swap(READMED_PATH,
            r'<!-- STATS:START -->.*?<!-- STATS:END -->',
            '<!-- STATS:START -->\n' + note + '\n\n' + table + '\n<!-- STATS:END -->',
            'README 数据速览'):
        print('  README.md 数据速览（%d 版卡牌 / %d 件道具 / %d 格）'
              % (len(versions), len(props['items']), s['total']))


def validate_map(data):
    """棋盘 JSON 的体检清单：数量、编号连续性、颜色分组引用、类型表覆盖。"""
    errs = []
    tiles = data.get('tiles') or []
    board = data.get('board') or {}
    if tiles:
        ids = [t['id'] for t in tiles]
        if ids != list(range(len(ids))):
            errs.append('格子 id 不是从 0 连续的（%s…%s）' % (ids[0], ids[-1]))
    n_expect = board.get('tilesPerSide', 15) * 4 + board.get('corners', 4)   # 四边各 15 格 + 4 个角格
    if tiles and len(tiles) != n_expect:
        errs.append('格子总数 %d ≠ 四边 %s×4 + %s 个角格 = %d'
                    % (len(tiles), board.get('tilesPerSide', 15), board.get('corners', 4), n_expect))
    if not board.get('printMM'):
        errs.append('board.printMM（成品边长 mm）没填，打印尺寸没法算')

    ids = {g['id'] for g in data.get('colorGroups') or []}
    for t in tiles:
        if 'colorId' in t and t['colorId'] not in ids:
            errs.append('格子 #%s 的 colorId=%s 在 colorGroups 里找不到' % (t['id'], t['colorId']))
        if t.get('price') is not None and t.get('colorId') is None:
            errs.append('格子 #%s（%s）有价格却没 colorId' % (t['id'], t.get('name')))
        if (t.get('type') or 'property') == 'property' and not t.get('flag'):
            errs.append('格子 #%s（%s）缺 flag（国旗 emoji），页面会画成白旗' % (t['id'], t.get('name')))

    types = data.get('tileTypes') or {}
    decks = data.get('decks') or {}
    used = {(t.get('type') or 'property') for t in tiles}
    for k in sorted(used - set(types)):
        errs.append('格子类型 "%s" 在 tileTypes 里没定义（图例会漏）' % k)
    for k, meta in types.items():
        if meta.get('deck') and meta['deck'] not in decks:
            errs.append('tileTypes.%s.deck = "%s"，decks 里没有这个牌堆' % (k, meta['deck']))
    return errs


def load_map_data():
    """读 content/map-print-data.json 并跑一遍体检；有错就返回 None（不写任何生成物）。"""
    if not os.path.exists(MAP_DATA_PATH):
        print('  跳过：未找到 map-print-data.json')
        return None
    with open(MAP_DATA_PATH, encoding='utf-8') as f:
        data = json.load(f)
    errs = validate_map(data)
    if errs:
        print('  !! map-print-data.json 校验未通过：')
        for e in errs:
            print('     - ' + e)
        return None
    return data


def write_map_print_fallback(data):
    """map-print-data.json → map-print-svg.html 的内置兜底块（本地 file:// 打开时用）"""
    if not data:
        return
    js = json.dumps(data, ensure_ascii=False, indent=2).replace('<', '\\u003c')
    block = ('/* MAP_FALLBACK:START */  // 由 tools/update.py 从 content/map-print-data.json 生成，请勿手改\n'
             '%s\n'
             '/* MAP_FALLBACK:END */' % js)
    for path in (MAP_SVG_PRINT_PATH,):
        if not os.path.exists(path):
            continue
        if swap(path, r'\/\* MAP_FALLBACK:START \*\/.*?\/\* MAP_FALLBACK:END \*\/', block, '棋盘兜底数据'):
            print('  %s 内置兜底（%d 格 / %d 个颜色组）'
                  % (os.path.basename(path), len(data['tiles']), len(data['colorGroups'])))


def main():
    print('读取 %s' % CSV_PATH)
    rows = fix_plus(load_rows())
    errs = validate(rows)
    if errs:
        print('\n校验未通过，未改动任何文件：')
        for e in errs:
            print('  - ' + e)
        sys.exit(1)
    data = build(rows)

    print('生成规则区：')
    global MAP_DATA
    MAP_DATA = load_map_data()          # 先读棋盘数据：资料页的表格要靠它遍历
    rules_html = build_rules()
    props_html = build_props()
    original_html = build_original()

    print('写入：')
    write_json(data)
    write_index(data, rules_html, props_html)
    write_original(original_html)
    write_print_fallback(data)
    props = parse_props()
    write_props(props)
    write_map_print_fallback(MAP_DATA)
    if MAP_DATA:
        write_map_info(MAP_DATA)
        write_readme_stats(MAP_DATA, props or {'items': [], 'rules': []}, data)
    print('完成。')


if __name__ == '__main__':
    main()
