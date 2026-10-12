#!/usr/bin/env python3
# 一键更新：cards.csv → cards.json + index.html（首页）+ print.html（打印页）
#
#   python3 tools/update.py
#
# 做四件事：
#   1. 校验 cards.csv（结构、必填字段、每版本张数）
#   2. 生成 cards.json                      —— 打印页线上 fetch 用
#   3. 重写 index.html 的卡牌数据、规则三版切换区、道具清单 —— 首页内容（静态，离线可看）
#   4. 回写 print.html 的内置兜底数据         —— 本地 file:// 打开时用
#   5. 重写 original.html 的原版资料区        —— 原版资料页
#
# 校验不通过就不写任何文件。GitHub Actions 跑的是同一个脚本。
import csv
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, 'cards.csv')
JSON_PATH = os.path.join(ROOT, 'cards.json')
PROPS_JSON_PATH = os.path.join(ROOT, 'props.json')
INDEX_PATH = os.path.join(ROOT, 'index.html')
PRINT_PATH = os.path.join(ROOT, 'print.html')
PROPS_PATH = os.path.join(ROOT, 'docs', 'props.md')
ORIGINAL_DIR = os.path.join(ROOT, 'original')
ORIGINAL_PATH = os.path.join(ROOT, 'original.html')
# 原版实体资料：文件名 → 页面上的区块标题（None = 直接用 md 里的一级标题）→ 是否默认展开
ORIGINAL_DOCS = [
    ('cards.md', '原版命运牌 & 机会牌（20 + 20 张）', True),
    ('manual.md', None, True),
    ('map-data-guide.md', '地图数据使用指南（速览 · 投资建议 · FAQ）', False),
    ('map-tiles.md', '原版地图格子数据（64 格 · 11 个颜色组）', False),
]

# 首页「游戏规则」区：三版并列，点卡片切换
#   (key, 卡片主标题, 卡片副标题, md 路径, 页面里的源文件链接, 链接前缀, 要折叠的小节)
#   折叠小节 = (标题层级, 标题关键字, 是否折到文末, 折叠后显示的标题 / None = 用原标题)
RULE_DOCS = [
    ('original', '原版', '实体说明书',
     os.path.join(ORIGINAL_DIR, 'manual.md'), 'original/manual.md', 'original/', []),
    ('v1', 'v1', '初版改版规则',
     os.path.join(ROOT, 'docs', 'rules.md'), 'docs/rules.md', 'docs/',
     [(3, '卡牌', True, '卡牌（cards.csv 与历史存档）'),
      (4, '备选', False, None)]),
    ('v2', 'v2', '最新改版规则',
     os.path.join(ROOT, 'docs', 'new-rule.md'), 'docs/new-rule.md', 'docs/', []),
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
def inline(t, prefix='docs/'):
    t = html.escape(t)
    t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'`(.+?)`', r'<code>\1</code>', t)
    t = re.sub(r'\[(.+?)\]\((?!https?:|#)(.+?)\)', r'<a href="%s\2">\1</a>' % prefix, t)
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


def md_to_html(md, prefix='docs/'):
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
    """把 docs/props.md 转成首页「道具清单」区的内容。"""
    if not os.path.exists(PROPS_PATH):
        print('  跳过：未找到 docs/props.md')
        return ''
    with open(PROPS_PATH, encoding='utf-8') as f:
        return md_to_html(f.read(), prefix='docs/')


def parse_props():
    """从 docs/props.md 里抽出结构化道具数据：使用规则 + 道具列表（用于打印页）。

    真源仍然是 props.md（首页道具清单也由它生成），这里只是把 md 里的表格和
    编号列表读成 dict，给打印页做道具卡用。改道具请改 props.md，别改 props.json。
    """
    if not os.path.exists(PROPS_PATH):
        print('  跳过：未找到 docs/props.md')
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
        print('  跳过：docs/props.md 里没解析到道具表格')
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
    block = ('  /* PROPS:START */  // 由 tools/update.py 从 docs/props.md 生成，请勿手改\n'
             '  %s\n'
             '  /* PROPS:END */' % js)
    if swap(PRINT_PATH, r'[ \t]*\/\* PROPS:START \*\/.*?\/\* PROPS:END \*\/', block, '道具兜底数据'):
        print('  props.json + print.html 内置道具兜底（%d 件道具，%d 条规则）'
              % (len(props['items']), len(props['rules'])))


def build_original():
    """把 original/ 下的原版实体资料转成 original.html 的正文区块。"""
    parts = []
    for fn, label, opened in ORIGINAL_DOCS:
        path = os.path.join(ORIGINAL_DIR, fn)
        if not os.path.exists(path):
            print('  跳过：未找到 original/%s' % fn)
            continue
        with open(path, encoding='utf-8') as f:
            text = f.read()
        if label is None:                      # 没写死标题就跟 md 的一级标题走
            label = md_title(text) or fn
        parts.append('<details class="blk"%s><summary><h2>%s</h2><span class="tog"></span></summary>\n'
                     '<div class="md">\n%s\n</div>\n</details>'
                     % (' open' if opened else '', html.escape(label), md_to_html(text, prefix='original/')))
    return '\n'.join(parts)


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
    rules_html = build_rules()
    props_html = build_props()
    original_html = build_original()

    print('写入：')
    write_json(data)
    write_index(data, rules_html, props_html)
    write_original(original_html)
    write_print_fallback(data)
    write_props(parse_props())
    print('完成。')


if __name__ == '__main__':
    main()
