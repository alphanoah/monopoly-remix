"""生成 data/cards.json 和 data/props.json。"""
import json
import os

from lib import ctx as ctxlib
from lib import paths

TITLE = '生成 data/*.json'


def run(ctx):
    data = ctxlib.cards(ctx)
    with open(paths.CARDS_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('  cards.json（%d 个版本，默认 %s）' % (len(data['versions']), data['default']))

    props = ctxlib.props(ctx)
    if props:
        with open(paths.PROPS_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(props, f, ensure_ascii=False, indent=2)
            f.write('\n')
        print('  props.json（%d 件道具，%d 条规则）' % (len(props['items']), len(props['rules'])))
