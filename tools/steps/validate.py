"""在写任何文件之前，把所有真源重新校验一遍。

卡牌（cards.md）校验不过 → 直接退出、不写任何文件（硬约束）。
棋盘（map-print-data.json）校验不过 → 只打印错误，地图相关块跳过，不阻断其余生成。
道具（props.md）读不到 → 只打印错误，道具相关块跳过。

这个步骤可以单独跑 `--step validate`，也可以在全量构建时作为第一道闸。
"""
import sys

from lib import ctx as ctxlib
from lib import paths

TITLE = '校验真源'


def run(ctx):
    # 卡牌：硬约束 —— 不过就退
    data = ctxlib.cards(ctx)
    print('  卡牌校验通过：%d 个版本，默认 %s' % (len(data['order']), data['default']))

    # 棋盘：软失败，只报不拦
    board = ctxlib.board(ctx)
    if board is None:
        print('  棋盘校验未通过或文件缺失，地图相关块将跳过')
    else:
        print('  棋盘校验通过：%d 格 / %d 个颜色组' % (len(board['tiles']), len(board['colorGroups'])))

    # 道具：软失败
    props = ctxlib.props(ctx)
    if props is None:
        print('  道具未解析到，道具相关块将跳过')
    else:
        print('  道具校验通过：%d 件，%d 条规则' % (len(props['items']), len(props['rules'])))
