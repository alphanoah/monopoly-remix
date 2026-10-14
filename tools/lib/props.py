"""道具真源（source/props.md）的三种读法：
  1. build_props_rules_html() — 使用规则 <ol>（首页道具卡区块顶部静态展示）
  2. parse_props()            — 结构化 dict（打印页道具卡 + data/props.json）
  3. gen_props_json_block()   — 注入首页的内嵌 JSON（给 JS 动态渲染道具卡网格）
"""
import json
import os
import re

from lib import md as mdlib
from lib import paths


def build_props_rules_html():
    """把 source/props.md 的「使用规则」章节转成 <ol> HTML（首页静态展示，道具列表由 JS 渲染）。"""
    if not os.path.exists(paths.PROPS_PATH):
        print('  跳过：未找到 source/props.md')
        return ''
    with open(paths.PROPS_PATH, encoding='utf-8') as f:
        text = f.read()
    body = mdlib.md_to_html(text)
    # md_to_html 会把整篇 md 转成 HTML，截到 </ol> 就停（只留规则，道具表格和后续都不要）
    cut = body.find('</ol>')
    if cut == -1:
        return body
    return body[:cut + 5]


def parse_props():
    """从 source/props.md 里抽出结构化道具数据：使用规则 + 道具列表（用于打印页）。

    真源仍然是 source/props.md（首页道具清单也由它生成），这里只是把 md 里的表格和
    编号列表读成 dict，给打印页做道具卡用。改道具请改 source/props.md，别改 data/props.json。
    """
    if not os.path.exists(paths.PROPS_PATH):
        print('  跳过：未找到 source/props.md')
        return None
    rules, items, section = [], [], None
    with open(paths.PROPS_PATH, encoding='utf-8') as f:
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
        print('  跳过：source/props.md 里没解析到道具表格')
        return None
    return {'rules': rules, 'items': items}
