"""step 之间共享的「按需加载 + 缓存」：每个真源只解析一遍，结果挂在 ctx 上。

卡牌校验不过 = 直接退出（硬约束：校验不过不写任何文件）；
棋盘 / 道具读不到 = 返回 None，相关块跳过（与旧 update.py 的软失败行为一致）。
"""
import sys

from lib import cards as cards_lib
from lib import mapdata
from lib import props as props_lib


def cards(ctx):
    if 'cards' not in ctx:
        data = cards_lib.load()
        if data is None:
            print('未改动任何文件。')
            sys.exit(1)
        ctx['cards'] = data
    return ctx['cards']


def board(ctx):
    """棋盘数据（dict 或 None）。None = 文件缺失或校验没过，地图相关生成块自行跳过。"""
    if 'map' not in ctx:
        ctx['map'] = mapdata.load()
    return ctx['map']


def props(ctx):
    """结构化道具数据（dict 或 None）。"""
    if 'props' not in ctx:
        ctx['props'] = props_lib.parse_props()
    return ctx['props']
