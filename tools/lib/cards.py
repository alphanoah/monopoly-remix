"""卡牌真源（source/cards.md）的解析、校验与构建。

cards.md 的结构约定：## 版本号 · 版本名 → ### 机会牌 / ### 命运牌 → 每节一张表。
列名和列序固定（tools/import-cards.py 回导出来的就是这个格式），两种花色的列不同。
"""
import re

from lib import paths

DEFAULT_VERSION = 'v7'
KEEP = ['deck', 'face', 'event', 'effect', 'cond', 'win', 'lose', 'rate']
# 金额字段：Excel / Numbers 存 CSV 时会把「+3000」当数值丢掉正号；md 手写也常忘写，统一补回
AMOUNT_FIELDS = ('effect', 'win', 'lose')

DECK_NAMES = {'chance': '机会牌', 'fate': '命运牌'}
CHANCE_HEAD = ['编号', '表情', '事件', '效果', '命中率', '启用']
FATE_HEAD = ['编号', '事件', '判定', '赢', '输', '命中率', '启用']
CHANCE_COLS = ['seq', 'face', 'event', 'effect', 'rate', 'use']
FATE_COLS = ['seq', 'event', 'cond', 'win', 'lose', 'rate', 'use']

CARDS_MD_INTRO = """# 自制卡牌

> 这份文件是自制机会牌 / 命运牌的**唯一真源**：改卡牌改这里，跑 `python3 tools/build.py` 同步页面。
> 想用 Excel 批量改：首页「机会/命运卡牌」区有「导出」按钮（CSV / Excel），
> 改完跑 `python3 tools/import-cards.py 文件.csv` 就会把表格回导成本文件（版本名沿用这里的 `##` 小节标题）。
>
> 结构约定：`## 版本号 · 版本名` 分版本 → `### 机会牌` / `### 命运牌` 分花色 → 每节一张表。
> 列名、列序不能动；空单元格 = 该字段留空；金额写 `3000` 或 `+3000` 都行，脚本统一补正号；
> 单元格内容里要写竖线就转义成 `\\|`。字段含义见 [docs/card-fields.md](../docs/card-fields.md)。
"""


def split_md_row(line):
    """拆 md 表格行：`\\|` 是转义的竖线，不算列分界。"""
    cells = [c.strip().replace('\\|', '|') for c in re.split(r'(?<!\\)\|', line.strip())]
    if cells and cells[0] == '':
        cells.pop(0)
    if cells and cells and cells[-1] == '':
        cells.pop()
    return cells


def parse_cards_md(text):
    """把 cards.md 读成行 dict（与 csv.DictReader 的输出同构），外加版本标签。

    返回 (rows, labels, errs)：labels = {版本号: 页面下拉显示的版本名}（取自 ## 标题整行）；
    errs 是结构错误（表头不对、列数不对、缺小节等），有错就不该写任何文件。
    """
    rows, labels, errs = [], {}, []
    ver = deck = None
    lines = text.replace('\r\n', '\n').split('\n')
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        m = re.match(r'^##\s+(\S+)(?:\s*·\s*(.+))?$', s)
        if m:
            ver = m.group(1)
            labels[ver] = ('%s · %s' % (ver, m.group(2).strip())) if m.group(2) else ver.upper()
            deck = None
            i += 1
            continue
        if s.startswith('### '):
            t = s[4:].strip()
            deck = 'chance' if t.startswith('机会') else 'fate' if t.startswith('命运') else None
            if deck is None:
                errs.append('「%s」下的花色小节不认识：### %s（要以「机会」或「命运」开头）' % (ver or '?', t))
            i += 1
            continue
        if s.startswith('|'):
            where = '「%s」%s' % (ver or '?', DECK_NAMES.get(deck, '（缺 ### 花色小节）'))
            if not ver or not deck:
                errs.append(where + '：表格必须放在 ## 版本小节和 ### 花色小节下面')
                i += 1
                continue
            expect = CHANCE_HEAD if deck == 'chance' else FATE_HEAD
            head = split_md_row(s)
            if head != expect:
                errs.append('%s表头应为 | %s |，实际是 | %s |' % (where, ' | '.join(expect), ' | '.join(head)))
                i += 1
                continue
            if i + 1 >= len(lines) or not re.match(r'^[\s:|-]*\|[\s:|-]+\|[\s:|-]*$', lines[i + 1].strip()):
                errs.append('%s表头下面缺 |---|---| 分隔行' % where)
                i += 1
                continue
            i += 2
            cols = CHANCE_COLS if deck == 'chance' else FATE_COLS
            while i < len(lines) and lines[i].strip().startswith('|'):
                cells = split_md_row(lines[i])
                if len(cells) != len(cols):
                    errs.append('%s表格第 %d 行列数不对（%d 列，应为 %d 列）'
                                % (where, i + 1, len(cells), len(cols)))
                else:
                    row = {'version': ver, 'deck': deck}
                    row.update(dict(zip(cols, cells)))
                    rows.append(row)
                i += 1
            continue
        i += 1
    if not rows and not errs:
        errs.append('cards.md 里没解析到任何卡牌（需要 ## 版本 → ### 花色 → 表格 三层结构）')
    return rows, labels, errs


def cards_to_md(rows, labels):
    """把行 dict 写成 cards.md 文本（tools/import-cards.py 回导时用；列格式与 parse_cards_md 互逆）。"""
    def esc(v):
        return (v or '').strip().replace('|', '\\|')

    order = []
    for r in rows:
        v = (r.get('version') or '').strip()
        if v and v not in order:
            order.append(v)
    out = [CARDS_MD_INTRO]
    for v in order:
        out.append('## %s' % labels.get(v, v.upper()))
        out.append('')
        group = [r for r in rows if (r.get('version') or '').strip() == v]
        for deck, head, cols in (('chance', CHANCE_HEAD, CHANCE_COLS), ('fate', FATE_HEAD, FATE_COLS)):
            sub = [r for r in group if (r.get('deck') or '').strip() == deck]
            if not sub:
                continue
            out.append('### %s（%d 张）' % (DECK_NAMES[deck], len(sub)))
            out.append('')
            out.append('| ' + ' | '.join(head) + ' |')
            out.append('|' + '|'.join(['------'] * len(head)) + '|')
            for r in sub:
                out.append('| ' + ' | '.join(esc(r.get(c)) for c in cols) + ' |')
            out.append('')
    return '\n'.join(out).rstrip() + '\n'


def fix_plus(rows):
    """金额写成纯数字时补回正号（电子表格存 CSV 会丢掉 +，手写 md 也常漏）。

    只处理「整个格子就是一个正整数」的情况，含文字的（如「+2000，被举报者…」）
    会被判成文本保留，负数也不受影响。
    """
    n = 0
    for r in rows:
        for k in AMOUNT_FIELDS:
            v = (r.get(k) or '').strip()
            if re.fullmatch(r'\d+', v) and int(v) > 0:
                r[k] = '+' + v
                n += 1
    if n:
        print('  补回 %d 个金额的正号（写 3000 还是 +3000 都一样，脚本统一补 +）' % n)
    return rows


def validate(rows):
    errs = []
    count = {}
    for r in rows:
        v = (r.get('version') or '').strip()
        deck = (r.get('deck') or '').strip()
        where = '「%s」%s #%s：' % (v or '?', DECK_NAMES.get(deck, deck or '?'), r.get('seq') or '?')
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


def build(rows, labels):
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
            v: {'label': labels.get(v, v.upper()), 'cards': versions[v]} for v in order
        },
    }


def load(path=None):
    """读 cards.md → 补正号 → 校验 → build。校验不过就打印并返回 None（调用方不得写任何文件）。"""
    path = path or paths.CARDS_MD_PATH
    print('读取 %s' % path)
    with open(path, encoding='utf-8') as f:
        rows, labels, errs = parse_cards_md(f.read())
    rows = fix_plus(rows)
    errs += validate(rows)
    if errs:
        print('\n卡牌校验未通过：')
        for e in errs:
            print('  - ' + e)
        return None
    return build(rows, labels)
