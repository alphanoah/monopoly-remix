"""重写 README.md 的「数据速览」表格。数字全部从各真源现算。"""
import collections

from lib import ctx as ctxlib
from lib import html_block, mapdata, paths

TITLE = '刷新 README 数据速览'


def gen_readme_stats(ctx):
    data = ctxlib.board(ctx)
    if not data:
        return None
    props = ctxlib.props(ctx) or {'items': [], 'rules': []}
    cards = ctxlib.cards(ctx)

    s = mapdata.summary(data)
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
    note = ('> 这一节由 <code>tools/build.py</code> 从各真源统计后写入，'
            '改了 md / JSON 真源后跑一次脚本就会同步，**不要手改**。')
    return (r'<!-- STATS:START -->.*?<!-- STATS:END -->',
            '<!-- STATS:START -->\n' + note + '\n\n' + table + '\n<!-- STATS:END -->',
            'README.md 数据速览（%d 版卡牌 / %d 件道具 / %d 格）'
            % (len(versions), len(props['items']), s['total']))


def run(ctx):
    r = gen_readme_stats(ctx)
    if r and html_block.swap(paths.README_PATH, *r[:2], 'README 数据速览'):
        print('  ' + r[2])
