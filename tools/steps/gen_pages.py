"""重写三个页面的标记块：index.html（卡牌 / 规则 / 道具 / 地图说明 / 字段说明弹窗）、original.html、print.html（双兜底）。

每个生成器返回 (pattern, block, report) 交给 lib.html_block.apply_blocks 写块；
返回 None = 这个块这次跳过（如道具 md 缺失）。
"""
import html
import json
import os
import re

from lib import ctx as ctxlib
from lib import docs as docs_lib
from lib import html_block, mapdata, paths
from lib import md as mdlib
from lib import props as props_lib


# ---------- 首页「游戏规则」区：多版并列，点卡片切换 ----------
def build_rules(ctx):
    # 规则 md 里链到 docs/ 文档的链接指向渲染页 other/<同名>.html，别给用户裸 .md
    dmap = docs_lib.doc_map(ctxlib.docs(ctx))
    docs = []
    for key, name, desc, path, rel, prefix, folds in ctx['rule_docs']:
        if not os.path.exists(path):
            print('  跳过：未找到 %s' % rel)
            continue
        with open(path, encoding='utf-8') as f:
            text = f.read()
        body = mdlib.md_to_html(text, prefix=prefix)
        for level, keyword, to_end, title in folds:
            body = mdlib.fold(body, level, keyword, to_end, title)
        if dmap:
            body = re.sub(r'href="([^"]+)"',
                          lambda m: 'href="%s"' % dmap[m.group(1)]
                          if m.group(1) in dmap else m.group(0), body)
        docs.append({'key': key, 'name': name, 'desc': desc, 'rel': rel,
                     'title': mdlib.md_title(text) or name, 'body': body})
    if not docs:
        return '<p class="empty">规则文件都没找到，跑一次 <code>python3 tools/build.py</code>。</p>'
    default = ctx['default_rule']
    default = default if any(d['key'] == default for d in docs) else docs[-1]['key']

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

    note = ('<p class="rnote">规则迭代了多个版本，这里并列放好，点上面的卡片切换。'
            '<strong>原版</strong> = 实体《大富翁世界之旅（银牌）》说明书的原文，'
            '<strong>v1</strong> = 朋友初版，<strong>v2</strong> = 过渡版，'
            '<strong>v3</strong> = 现行版本（为什么这么定见 '
            '<a href="other/rule-changelog.html">规则修订记录</a>）。</p>')
    print('  规则版本：%s（默认 %s）' % (' / '.join(d['name'] for d in docs), default))
    return (note + '\n<div class="rtabs" role="tablist" aria-label="规则版本">\n' + '\n'.join(tabs) +
            '\n</div>\n<div class="rviews">\n' + '\n'.join(panes) + '\n</div>')


# ---------- 原版资料页 ----------
def title_for_cards(text, data):
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


def title_for_tiles(text, data):
    """原版地图区块标题：格数与颜色组数由棋盘 JSON 现算（没有数据时回退到 md 的概览表）。"""
    if data:
        s = mapdata.summary(data)
        return '原版地图格子数据（%d 格 · %d 个颜色组）' % (s['total'], s['groups'])
    import re
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


def build_original(ctx):
    """把 source/original/ 下的原版实体资料转成 original.html 的正文区块。

    md 里可以写 `{{STATS:xxx}}` 占位符，渲染时换成从 source/remix/map.json
    遍历出来的表格——地图那两篇的统计就不再是手抄的。
    """
    data = ctxlib.board(ctx)
    parts = []
    for fn, label, opened in ctx['original_docs']:
        path = os.path.join(paths.ORIGINAL_DIR, fn)
        if not os.path.exists(path):
            print('  跳过：未找到 source/original/%s' % fn)
            continue
        with open(path, encoding='utf-8') as f:
            text = f.read()
        if callable(label):                    # 给了个函数 = 按 md 内容现算的标题（张数/格数不写死）
            label = label(text, data)
        elif label is None:                    # 没写标题就跟 md 的一级标题走
            label = mdlib.md_title(text) or fn
        body = mdlib.md_to_html(text, prefix='source/original/')
        body = mapdata.render_map_stats(body, data)
        parts.append('<details class="blk"%s><summary><h2>%s</h2><span class="tog"></span></summary>\n'
                     '<div class="md">\n%s\n</div>\n</details>'
                     % (' open' if opened else '', html.escape(label), body))
    return '\n'.join(parts)


# ---------- 标记块生成器（在 build.py 的 PAGES 站点地图里被引用） ----------
def gen_cards_js(ctx):
    data = ctxlib.cards(ctx)
    js = 'const DECKS = ' + json.dumps(data, ensure_ascii=False, indent=2).replace('<', '\\u003c') + ';'
    total = sum(len(data['versions'][v]['cards']) for v in data['order'])
    return (r'/\* CARDS:START \*/.*?/\* CARDS:END \*/',
            '/* CARDS:START */\n' + js + '\n/* CARDS:END */',
            'index.html 卡牌数据（%d 个版本共 %d 张）' % (len(data['order']), total))


def gen_rules_html(ctx):
    h = build_rules(ctx)
    return (r'<!-- RULES:START -->.*?<!-- RULES:END -->',
            '<!-- RULES:START -->\n' + h + '\n<!-- RULES:END -->',
            'index.html 规则区（%d 字符）' % len(h))


def gen_props_rules_html(ctx):
    h = props_lib.build_props_rules_html()
    if not h:
        return None
    return (r'<!-- PROPS_RULES:START -->.*?<!-- PROPS_RULES:END -->',
            '<!-- PROPS_RULES:START -->\n' + h + '\n<!-- PROPS_RULES:END -->',
            'index.html 道具规则（%d 字符）' % len(h))


def gen_props_js(ctx):
    """把道具数据序列化成 const PROPS = {...} 注入 index.html，供 JS 动态渲染道具卡网格。"""
    props = props_lib.parse_props()
    if not props:
        return None
    js = ('const PROPS = ' +
          json.dumps(props, ensure_ascii=False, indent=2).replace('<', '\\u003c') + ';')
    return (r'/\* PROPS_DATA:START \*/.*?/\* PROPS_DATA:END \*/',
            '/* PROPS_DATA:START */\n' + js + '\n/* PROPS_DATA:END */',
            'index.html 道具数据（%d 件道具）' % len(props['items']))


def gen_map_info(ctx):
    """首页「电子地图」区的说明文字：格子数、各类格子、颜色组数、成品尺寸全部从 JSON 现算。"""
    data = ctxlib.board(ctx)
    if not data:
        return None
    s = mapdata.summary(data)
    block = (
        '  <p class="meta">电子版「世界之旅」棋盘：<strong>{total}</strong> 格全图'
        '（{detail}，{groups} 个颜色组），地产均价 ${avg:,}。'
        '两档视图：<strong>打印版</strong>（按实体棋盘一比一还原）/ '
        '<strong>放大版</strong>（跑道加厚吃进中间空、文字竖排放大，手机上也能看清）。'
        '整板固定一屏放下，可按颜色组筛选、导出 PNG。<br>'
        '要实体棋盘：点页面里的「打印」直接出 <strong>{cm}×{cm}cm</strong> 见方（{mm}×{mm}mm）、'
        '边距无、勾选「背景图形」。</p>'
    ).format(**s)
    return (r'<!-- MAPINFO:START -->.*?<!-- MAPINFO:END -->',
            '<!-- MAPINFO:START -->\n' + block + '\n  <!-- MAPINFO:END -->',
            'index.html 电子地图区（%d 格 / %d 组 / %scm）' % (s['total'], s['groups'], s['cm']))


def gen_card_fields_quick(ctx):
    """首页卡牌区「字段说明」弹窗：docs/card-fields.md 里 QUICK 标记包住的速查节。

    弹窗只放速查节（短，看完即走），完整文档在 other/card-fields.html（gen_docs 生成）。
    """
    if not os.path.exists(paths.CARDFIELDS_MD_PATH):
        print('  跳过：未找到 docs/card-fields.md')
        return None
    with open(paths.CARDFIELDS_MD_PATH, encoding='utf-8') as f:
        text = f.read()
    m = re.search(r'<!--\s*QUICK:START\s*-->(.*?)<!--\s*QUICK:END\s*-->', text, re.S)
    if not m:
        print('  !! docs/card-fields.md 里没有 QUICK:START/END 标记块，弹窗内容跳过')
        return None
    body = mdlib.md_to_html(mdlib.strip_comments(m.group(1)), prefix='docs/')
    return (r'<!-- CARD_FIELDS_QUICK:START -->.*?<!-- CARD_FIELDS_QUICK:END -->',
            '<!-- CARD_FIELDS_QUICK:START -->\n' + body + '\n<!-- CARD_FIELDS_QUICK:END -->',
            'index.html 字段说明弹窗（%d 字符）' % len(body))


def gen_original_html(ctx):
    h = build_original(ctx)
    return (r'<!-- ORIGINAL:START -->.*?<!-- ORIGINAL:END -->',
            '<!-- ORIGINAL:START -->\n' + h + '\n<!-- ORIGINAL:END -->',
            'original.html（%d 字符）' % len(h))


def gen_print_fallback(ctx):
    """默认版本的卡牌兜底：本地 file:// 打开 print.html 时 fetch 会被拦，用这份。"""
    data = ctxlib.cards(ctx)
    vid = data['default']
    cards = data['versions'][vid]['cards']
    js = 'const FALLBACK = ' + json.dumps(
        {'version': vid, 'label': data['versions'][vid]['label'], 'cards': cards},
        ensure_ascii=False, indent=2).replace('<', '\\u003c') + ';'
    block = ('  /* FALLBACK:START */  // 由 tools/build.py 生成，请勿手改\n'
             '  %s\n'
             '  /* FALLBACK:END */' % js)
    return (r'[ \t]*\/\* FALLBACK:START \*\/.*?\/\* FALLBACK:END \*\/',
            block,
            'print.html 内置兜底（%s，%d 张）' % (vid, len(cards)))


def gen_props_fallback(ctx):
    props = ctxlib.props(ctx)
    if not props:
        return None
    js = ('const PROPS_FALLBACK = ' +
          json.dumps(props, ensure_ascii=False, indent=2).replace('<', '\\u003c') + ';')
    block = ('  /* PROPS:START */  // 由 tools/build.py 从 source/remix/props.md 生成，请勿手改\n'
             '  %s\n'
             '  /* PROPS:END */' % js)
    return (r'[ \t]*\/\* PROPS:START \*\/.*?\/\* PROPS:END \*\/',
            block,
            'print.html 内置道具兜底（%d 件道具，%d 条规则）' % (len(props['items']), len(props['rules'])))


GENERATORS = {
    'cards_js': gen_cards_js,
    'rules_html': gen_rules_html,
    'props_data': gen_props_js,
    'props_rules': gen_props_rules_html,
    'map_info': gen_map_info,
    'card_fields_quick': gen_card_fields_quick,
    'original_html': gen_original_html,
    'print_fallback': gen_print_fallback,
    'props_fallback': gen_props_fallback,
}

TITLE = '重写 index.html / original.html / print.html'
FILES = {'index.html', 'original.html', 'print.html'}


def run(ctx):
    for rel, blocks in ctx['pages']:
        if rel not in FILES:
            continue
        html_block.apply_blocks(
            os.path.join(paths.ROOT, rel),
            [(marker, GENERATORS[name]) for marker, name in blocks], ctx)
