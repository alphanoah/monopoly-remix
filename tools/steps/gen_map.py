"""把 map.json 的内置兜底写进 map.html（本地 file:// 打开时用）。"""
import json
import os

from lib import ctx as ctxlib
from lib import html_block, paths

TITLE = '回写地图页兜底'


def gen_map_fallback(ctx):
    data = ctxlib.board(ctx)
    if not data:
        return None
    js = json.dumps(data, ensure_ascii=False, indent=2).replace('<', '\\u003c')
    block = ('/* MAP_FALLBACK:START */  // 由 tools/build.py 从 source/remix/map.json 生成，请勿手改\n'
             '%s\n'
             '/* MAP_FALLBACK:END */' % js)
    return (r'\/\* MAP_FALLBACK:START \*\/.*?\/\* MAP_FALLBACK:END \*\/',
            block,
            '%s 内置兜底（%d 格 / %d 个颜色组）' % (os.path.basename(paths.MAP_PATH), len(data['tiles']), len(data['colorGroups'])))


def run(ctx):
    r = gen_map_fallback(ctx)
    if r:
        html_block.swap(paths.MAP_PATH, *r[:2], '棋盘兜底数据')
        print('  ' + r[2])
