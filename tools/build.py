#!/usr/bin/env python3
# 一键更新：source/ 真源 → data/*.json + index.html（首页）+ original.html（原版资料页）
#                            + print.html（打印页）+ map.html（电子地图）+ README.md（数据速览）
#
#   python3 tools/build.py                    全部跑一遍
#   python3 tools/build.py --step gen_pages   只跑某一步（可逗号多个：--step gen_data,gen_pages）
#
# 步骤见下面 STEPS；页面与标记块的对应关系见 PAGES 站点地图。
# 卡牌校验不通过就不写任何文件。GitHub Actions 跑的是同一个脚本。
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import paths  # noqa: F401  路径统一在 lib/paths.py
from steps import validate, gen_data, gen_pages, gen_map, gen_readme

# 首页「游戏规则」区：三版并列，点卡片切换
#   (key, 卡片主标题, 卡片副标题, md 路径, 页面里的源文件链接, 链接前缀, 要折叠的小节)
#   折叠小节 = (标题层级, 标题关键字, 是否折到文末, 折叠后显示的标题 / None = 用原标题)
RULE_DOCS = [
    ('original', '原版', '实体说明书',
     os.path.join(paths.ORIGINAL_DIR, 'manual.md'), 'source/original/manual.md',
     'source/original/', []),
    ('v1', 'v1', '初版改版规则',
     os.path.join(paths.SOURCE_DIR, 'rules.md'), 'source/rules.md', 'source/',
     [(3, '卡牌', True, '卡牌（cards.md 与历史存档）'),
      (4, '备选', False, None)]),
    ('v2', 'v2', '最新改版规则',
     os.path.join(paths.SOURCE_DIR, 'new-rule.md'), 'source/new-rule.md', 'source/', []),
]
DEFAULT_RULE = 'v2'

# 原版实体资料（original.html）：文件名 → 区块标题（None = 用 md 里的一级标题；函数 = 按内容现算）
#                                 → 是否默认展开
#   标题里的张数 / 格数不写死：改了 md 表格，区块标题自动跟着变
ORIGINAL_DOCS = [
    ('cards.md', gen_pages.title_for_cards, True),
    ('manual.md', None, True),
    ('map-data-guide.md', '地图数据使用指南（速览 · 投资建议 · FAQ）', False),
    ('map-tiles.md', gen_pages.title_for_tiles, False),
]

# 站点地图：页面 → [(标记块, 生成器名)]。生成器在各 step 模块的 GENERATORS 里注册，这里只声明「谁喂谁」。
# 加新区块 = 在对应 step 里写生成器 + 在这里登记一行。
PAGES = [
    ('index.html', [
        ('CARDS', 'cards_js'),           # const DECKS = 卡牌全量数据
        ('RULES', 'rules_html'),         # 规则三版切换区（RULE_DOCS）
        ('PROPS', 'props_html'),         # 道具清单（source/props.md 整篇转 HTML）
        ('MAPINFO', 'map_info'),         # 「电子地图」区说明（格子数/尺寸现算）
    ]),
    ('original.html', [
        ('ORIGINAL', 'original_html'),   # 原版资料区块（ORIGINAL_DOCS + {{STATS}} 现算表格）
    ]),
    ('print.html', [
        ('FALLBACK', 'print_fallback'),  # 默认版本卡牌兜底（本地 file:// 打开时用）
        ('PROPS', 'props_fallback'),     # 道具兜底（同源，print.html 里是 /* */ 注释标记）
    ]),
    ('map.html', [
        ('MAP_FALLBACK', 'map_fallback'),  # 棋盘数据兜底（gen_map）
    ]),
    ('README.md', [
        ('STATS', 'readme_stats'),       # 「数据速览」表格（gen_readme）
    ]),
]

STEPS = [
    ('validate', validate),
    ('gen_data', gen_data),
    ('gen_pages', gen_pages),
    ('gen_map', gen_map),
    ('gen_readme', gen_readme),
]


def main():
    ap = argparse.ArgumentParser(description='source/ 真源 → 各页面与 data/*.json 的一键构建')
    ap.add_argument('--step', help='只跑指定步骤（逗号分隔多个）：' + '、'.join(n for n, _ in STEPS))
    args = ap.parse_args()

    selected = set(args.step.split(',')) if args.step else None
    names = {n for n, _ in STEPS}
    if selected and selected - names:
        print('不认识步骤：%s（可选：%s）' % ('、'.join(sorted(selected - names)), '、'.join(n for n, _ in STEPS)))
        sys.exit(1)

    ctx = {
        'rule_docs': RULE_DOCS,
        'original_docs': ORIGINAL_DOCS,
        'default_rule': DEFAULT_RULE,
        'pages': PAGES,
    }
    for name, mod in STEPS:
        if selected and name not in selected:
            continue
        print('【%s】' % mod.TITLE)
        mod.run(ctx)
    print('完成。')


if __name__ == '__main__':
    main()
