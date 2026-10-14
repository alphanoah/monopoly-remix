"""棋盘真源（source/map-print-data.json）的读取、校验与统计渲染。

两档布局（打印版/放大版）共用这一份 JSON；统计表格给 original.html 的 {{STATS:key}} 占位符、
首页「电子地图」区和 README「数据速览」用，数字全部现算不写死。
"""
import collections
import html
import json
import os
import re

from lib import paths

SIDE_CN = {'bottom': '底行', 'left': '左行', 'top': '顶行', 'right': '右行'}
EDGES = [('bottom', 0, 16), ('left', 16, 32), ('top', 32, 48), ('right', 48, 0)]   # 四条边：起点角 → 终点角


# ---------- 读取与校验 ----------
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

    # 变体（variants.v2 等）：格子 id 必须存在、替换后的类型必须在 tileTypes 里
    tile_ids = {t['id'] for t in tiles}
    for vname, var in (data.get('variants') or {}).items():
        if vname == 'note' or not isinstance(var, dict):
            continue
        for tid, patch in (var.get('replace') or {}).items():
            if int(tid) not in tile_ids:
                errs.append('variants.%s 要替换的格子 #%s 不存在' % (vname, tid))
            if patch.get('type') and patch['type'] not in types:
                errs.append('variants.%s 把 #%s 换成类型 "%s"，tileTypes 里没定义' % (vname, tid, patch['type']))
    return errs


def load(path=None):
    """读 map-print-data.json 并跑一遍体检；有错就打印并返回 None（地图相关的块跳过不写）。"""
    path = path or paths.MAP_DATA_PATH
    if not os.path.exists(path):
        print('  跳过：未找到 map-print-data.json')
        return None
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    errs = validate_map(data)
    if errs:
        print('  !! map-print-data.json 校验未通过：')
        for e in errs:
            print('     - ' + e)
        return None
    return data


# ---------- 速览统计 ----------
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


def summary(data):
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


# ---------- 原版资料页的 {{STATS:key}} 表格：全部从棋盘 JSON 遍历出来 ----------
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
        if counts.get(k, 0) == 0:
            continue        # 只列棋盘上真有的类型（jail/shop 等 v2 变体类型别在原版资料页冒 0）
        rows.append([meta['name'], counts[k], meta.get('desc', '')])
    return md_table(['类型', '数量', '说明'], rows)


def stats_overview(data):
    counts = type_counts(data)
    rows = [['总格数', len(data['tiles'])], ['地产格', '%d 个' % counts.get('property', 0)]]
    for k, meta in data['tileTypes'].items():
        if k == 'property' or counts.get(k, 0) == 0:
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
    s = summary(data)
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


def render_map_stats(body, data):
    """把 md 里的 {{STATS:key}} 占位符换成从棋盘 JSON 现算的表格（没有数据时给个提示）。"""
    miss = '<p class="empty">棋盘数据没读到：先跑一次 tools/build.py 生成 map-print-data.json 的兜底。</p>'
    for key, fn in MAP_STATS.items():
        marker = '<p>{{STATS:%s}}</p>' % key
        if marker in body:
            body = body.replace(marker, fn(data) if data else miss)
    unknown = sorted(set(re.findall(r'\{\{STATS:([a-zA-Z]+)\}\}', body)))
    if unknown:
        print('  !! 资料 md 里有不认识的统计占位符：%s（可用：%s）'
              % ('、'.join(unknown), '、'.join(MAP_STATS)))
    return body
