"""docs/ 文档的扫描与元数据。gen_docs（渲染 other/）与 gen_pages（规则区互链重写）共用一份清单。

约定（写文档的人只看这段就够了）：
- `docs/` 下的 md **默认全部发布**成 `other/<同名>.html`，不用去 build.py 登记。
  不想发布的草稿文件名以 `_` 开头（如 `_草稿.md`）。
- 元数据写在 md 顶部的单行 HTML 注释里，`<!-- 键: 值 -->`。
  它们是注释，`lib/md.py` 的 `strip_comments` 会剥掉，不会进正文：
    cat     索引页分组，缺省「其他」
    blurb   一句话简介（页头副标题 + 索引卡片）
    order   组内排序号，缺省 99；同号按文件名字母序
    status  页面顶部的状态提示条（如「已被 strategy-v3 取代」），缺省不显示

加新文档 = 往 docs/ 丢一个 md，写完元数据注释，跑一次 build.py。
"""
import os
import re

from lib import md as mdlib
from lib import paths

# 索引页的分类顺序与每类的引导语。没登记的分类排在最后。
CATS = [
    ('攻略', '打法与决策：这张牌该不该接、这步该不该买'),
    ('规则', '规则迭代的审查与修订记录：现在这么定，是因为当初踩过什么'),
    ('平衡性', '卡牌 / 道具 / 节奏的实测数据'),
    ('维护', '改数据时的操作手册：字段怎么填、怎么导出回导'),
]
DEFAULT_CAT = '其他'

META_RE = re.compile(r'^\s*<!--\s*([a-z]+):\s*(.*?)\s*-->\s*$')
DEFAULT_ORDER = 99


def cat_order(cat):
    names = [c for c, _ in CATS]
    return names.index(cat) if cat in names else len(names)


def parse_meta(text):
    """抽 md 顶部的单行 `<!-- 键: 值 -->` 注释。只看前 20 行，正文里的注释不算元数据。"""
    meta = {}
    for line in text.splitlines()[:20]:
        m = META_RE.match(line)
        if m:
            meta[m.group(1)] = m.group(2)
    return meta


def load(docs_dir=None):
    """扫描 docs/ 返回已排序的文档清单：[{name,title,cat,blurb,order,status,rel,path}]"""
    d = docs_dir or paths.DOCS_DIR
    if not os.path.isdir(d):
        return []
    docs = []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith('.md') or fn.startswith('_'):
            continue
        name = fn[:-3]
        path = os.path.join(d, fn)
        with open(path, encoding='utf-8') as f:
            text = f.read()
        meta = parse_meta(text)
        order = DEFAULT_ORDER
        if 'order' in meta:
            try:
                order = int(meta['order'])
            except ValueError:
                print('  警告：docs/%s.md 的 order 不是数字，按顺序排到最后' % name)
        docs.append({
            'name': name,
            'path': path,
            'title': mdlib.md_title(text) or name,
            'cat': meta.get('cat') or DEFAULT_CAT,
            'blurb': meta.get('blurb') or '',
            'order': order,
            'status': meta.get('status') or '',
        })
    docs.sort(key=lambda x: (cat_order(x['cat']), x['order'], x['name']))
    return docs


def doc_map(docs):
    """站点根路径 → other/ 渲染页，给规则 md 等内容的互链重写用。"""
    return {'docs/%s.md' % x['name']: 'other/%s.html' % x['name'] for x in docs}


def group(docs):
    """按 cat 分组，返回 [(cat, [doc...])]，顺序同 CATS。"""
    order = [c for c, _ in CATS]
    seen = {}
    for x in docs:
        seen.setdefault(x['cat'], []).append(x)
    known = [(c, seen[c]) for c in order if c in seen]
    extra = [(c, seen[c]) for c in sorted(seen) if c not in order]
    return known + extra
