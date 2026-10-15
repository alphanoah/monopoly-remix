"""把 docs/ 下的 md 全量转成 other/ 目录的独立 HTML 页面，外加索引页 other/index.html。

不用在 build.py 登记文档清单——**扫描 docs/ 目录即可**：`.md` 默认都发布，`_` 开头的是草稿不发布。
文档的分类 / 简介 / 排序 / 状态提示写在 md 头顶的单行注释里，解析逻辑见 `lib/docs.py` 顶部说明。

链接重写：md_to_html 会把相对链接折叠成相对站点根的路径（如 docs/x.md、source/remix/map.json），
对根目录页面是对的，但 other/ 是子目录——指向 docs/ 内文档的链接改写成 other/<同名>.html，
其余站内相对链接加 ../ 前缀；http(s) 与 # 锚点不动。同一套重写规则给 gen_pages 用（见 lib/docs.doc_map）。
"""
import html
import os
import re

from lib import ctx as ctxlib
from lib import docs as docs_lib
from lib import md as mdlib
from lib import paths

TITLE = '生成 other/ 文档页'

# 与 original.html 同一套视觉（米白底 / 玫红点缀），去掉 details 相关样式
CSS = """
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    background: #fbfaf8; color: #2c2c2a;
    font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", system-ui, sans-serif;
    line-height: 1.7; -webkit-font-smoothing: antialiased;
  }
  .wrap { max-width: 980px; margin: 0 auto; padding: 0 20px; }

  header { padding: 40px 0 24px; border-bottom: 1px solid #e8e5df; }
  header h1 { font-size: 24px; font-weight: 500; margin: 0 0 10px; letter-spacing: .3px; }
  header p { margin: 0; color: #6b6a66; font-size: 14.5px; max-width: 680px; }
  .nav { display: flex; flex-wrap: wrap; gap: 16px; font-size: 13.5px; margin: 0 0 18px; }
  .nav a { color: #96597A; text-decoration: none; border-bottom: 1px solid #e8e5df; }
  .nav a:hover { border-color: #96597A; }

  .guide {
    margin: 18px 0 0; padding: 12px 16px; background: #fff; border: 1px solid #e8e5df;
    border-radius: 10px; font-size: 13.5px; color: #6b6a66; line-height: 1.7;
  }
  .guide b { color: #2c2c2a; font-weight: 500; }
  .guide a { color: #96597A; text-decoration: none; border-bottom: 1px solid #e8e5df; }

  .status {
    margin: 18px 0 0; padding: 10px 16px; border-radius: 8px; font-size: 13.5px;
    background: #fdf6e9; border: 1px solid #e8d9b4; color: #7a5f2a;
  }

  .md { font-size: 14.5px; padding: 8px 0 10px; }
  .md h3 { font-size: 17px; font-weight: 500; margin: 26px 0 10px; }
  .md h4 { font-size: 15px; font-weight: 500; margin: 20px 0 8px; color: #55534e; }
  .md h5 { font-size: 14px; font-weight: 500; margin: 16px 0 6px; color: #6b6a66; }
  .md ul, .md ol { margin: 6px 0; padding-left: 22px; }
  .md li { margin: 3px 0; }
  .md blockquote {
    margin: 12px 0; padding: 8px 14px; border-left: 3px solid #ddd9d2;
    color: #6b6a66; background: #f4f2ee; border-radius: 0 6px 6px 0;
  }
  .md code { background: #f0ede8; padding: 1px 5px; border-radius: 4px; font-size: 13px; }
  .md p { margin: 10px 0; }
  .md a { color: #96597A; }

  .tw { overflow-x: auto; margin: 10px 0; -webkit-overflow-scrolling: touch; }
  .md table { border-collapse: collapse; width: 100%; font-size: 13px; line-height: 1.5; }
  .md th, .md td { border: 1px solid #e5e1da; padding: 5px 9px; text-align: left; vertical-align: top; }
  .md th { background: #f4f2ee; font-weight: 500; white-space: nowrap; }

  .gcat { font-size: 15px; font-weight: 500; margin: 28px 0 2px; }
  .gcat span { font-weight: 400; font-size: 13px; color: #8a8880; margin-left: 10px; }

  .docs { list-style: none; margin: 14px 0 6px; padding: 0; display: grid; gap: 12px; }
  .docs a {
    display: block; padding: 14px 18px; background: #fff; border: 1px solid #e8e5df;
    border-radius: 10px; text-decoration: none; color: inherit;
  }
  .docs a:hover { border-color: #96597A; }
  .docs b { font-size: 15px; font-weight: 500; display: block; margin-bottom: 4px; }
  .docs span { font-size: 13px; color: #6b6a66; display: block; line-height: 1.55; }
  .docs em {
    font-style: normal; font-size: 11.5px; color: #96597A;
    background: #f6eef2; border-radius: 4px; padding: 1px 7px; margin-left: 8px;
  }
  .docs i {
    font-style: normal; font-size: 12.5px; color: #7a5f2a; display: block; margin-top: 5px;
  }

  footer { padding: 26px 0 60px; color: #8a8880; font-size: 13px; }
  footer code { background: #f0ede8; padding: 1px 5px; border-radius: 4px; font-size: 12px; }
  footer a { color: #6b6a66; text-decoration: none; border-bottom: 1px solid #ddd9d2; }

  @media (max-width: 600px) {
    header { padding: 30px 0 20px; }
    header h1 { font-size: 20px; }
    .md { font-size: 14px; }
  }
"""

PAGE_TMPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s · 大富翁改版</title>
<style>%(css)s</style>
</head>
<body>
<div class="wrap">
<header>
  <p class="nav"><a href="../index.html">← 首页</a><a href="index.html">更多文档</a></p>
  <h1>%(title)s</h1>
  <p>%(blurb)s</p>
%(status)s</header>
<div class="md">
%(body)s
</div>
<footer>本文由 <code>tools/build.py</code> 从 <code>docs/%(name)s.md</code> 生成，改文档改那份 md 再跑脚本。</footer>
</div>
</body>
</html>
"""

INDEX_TMPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>更多文档 · 大富翁改版</title>
<meta name="description" content="大富翁改版的分析文档：胜率攻略、卡牌与道具平衡性实测、规则审查记录、维护说明。">
<style>%(css)s</style>
</head>
<body>
<div class="wrap">
<header>
  <p class="nav"><a href="../index.html">← 首页</a></p>
  <h1>更多文档</h1>
  <p>改版过程中的推演与实测，每篇都由 <code>docs/</code> 下的同名 md 生成。</p>
  <p class="guide"><b>从哪看起</b>：只想开局 → 回<a href="../index.html">首页</a>，规则面板 + 卡牌区就够；
     想知道「为什么这么定」 → 看下面的<b>规则</b>与<b>平衡性</b>；要自己改数据 → 看<b>维护</b>。</p>
</header>
%(groups)s
<footer>由 <code>tools/build.py</code> 生成，共 %(count)d 篇。</footer>
</div>
</body>
</html>
"""

GROUP_TMPL = """<h3 class="gcat">%(cat)s<span>%(desc)s</span></h3>
<ul class="docs">
%(items)s
</ul>
"""

ITEM_TMPL = ('<li><a href="%(name)s.html"><b>%(title)s<em>%(cat)s</em></b>'
             '<span>%(blurb)s</span>%(status)s</a></li>')


def run(ctx):
    docs = ctxlib.docs(ctx)
    os.makedirs(paths.OTHER_DIR, exist_ok=True)

    # 清理已移除/改名的旧产物（md 删了或改名了，对应的 html 要跟着消失）
    keep = {x['name'] + '.html' for x in docs} | {'index.html'}
    for f in sorted(os.listdir(paths.OTHER_DIR)):
        if f.endswith('.html') and f not in keep:
            os.remove(os.path.join(paths.OTHER_DIR, f))
            print('  清理旧产物：other/' + f)

    dmap = docs_lib.doc_map(docs)

    def rewrite(m):
        href = m.group(1)
        if re.match(r'^[a-z]+:', href) or href.startswith('#'):
            return m.group(0)
        if href in dmap:
            return 'href="%s"' % dmap[href]       # 同目录的渲染页
        return 'href="../%s"' % href              # 其余站内相对链接（含未发布的草稿 md）

    for x in docs:
        with open(x['path'], encoding='utf-8') as f:
            text = f.read()
        body = mdlib.md_to_html(mdlib.strip_comments(text), prefix='docs/')
        body = re.sub(r'href="([^"]+)"', rewrite, body)
        status = ('<p class="status">%s</p>' % html.escape(x['status'])) if x['status'] else ''
        out = PAGE_TMPL % {'title': html.escape(x['title']), 'blurb': html.escape(x['blurb']),
                           'status': status, 'name': x['name'], 'body': body, 'css': CSS}
        with open(os.path.join(paths.OTHER_DIR, x['name'] + '.html'), 'w', encoding='utf-8') as f:
            f.write(out)

    descs = dict(docs_lib.CATS)
    blocks = []
    for cat, items in docs_lib.group(docs):
        lis = []
        for x in items:
            lis.append(ITEM_TMPL % {
                'name': x['name'], 'title': html.escape(x['title']), 'cat': html.escape(cat),
                'blurb': html.escape(x['blurb']),
                'status': ('<i>状态：%s</i>' % html.escape(x['status'])) if x['status'] else ''})
        blocks.append(GROUP_TMPL % {'cat': html.escape(cat),
                                    'desc': html.escape(descs.get(cat, '')),
                                    'items': '\n'.join(lis)})

    index = INDEX_TMPL % {'css': CSS, 'groups': '\n'.join(blocks), 'count': len(docs)}
    with open(os.path.join(paths.OTHER_DIR, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(index)

    skipped = [f for f in sorted(os.listdir(paths.DOCS_DIR)) if f.startswith('_')]
    print('  other/ 重写完：%d 篇文档 + 索引页%s'
          % (len(docs), ('（草稿跳过：%s）' % '、'.join(skipped)) if skipped else ''))
