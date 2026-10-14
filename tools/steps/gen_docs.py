"""把 docs/ 下的文档转成 other/ 目录的独立 HTML 页面，外加索引页 other/index.html。

文档清单在 build.py 顶部的 DOCS 里声明（文档名 / 类别 / 一句话简介），
页面标题自动取 md 的一级标题。

链接重写：md_to_html 会把相对链接折叠成相对站点根的路径（如 docs/x.md、original.html），
对根目录页面是对的，但 other/ 是子目录——指向 docs/ 内已登记文档的链接改写成同目录 .html，
其余站内相对链接加 ../ 前缀；http(s) 与 # 锚点不动。
"""
import html
import os
import re

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

  .docs { list-style: none; margin: 22px 0 6px; padding: 0; display: grid; gap: 12px; }
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
</header>
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
<meta name="description" content="大富翁改版的分析文档：胜率攻略、卡牌与道具平衡性实测、卡牌对照、维护说明。">
<style>%(css)s</style>
</head>
<body>
<div class="wrap">
<header>
  <p class="nav"><a href="../index.html">← 首页</a></p>
  <h1>更多文档</h1>
  <p>改版过程中的推演与实测：胜率攻略、卡牌与道具平衡性、卡牌对照、数据维护说明。
     这里每篇都由 <code>docs/</code> 下的同名 md 生成。</p>
</header>
<ul class="docs">
%(items)s
</ul>
<footer>由 <code>tools/build.py</code> 生成，共 %(count)d 篇。</footer>
</div>
</body>
</html>
"""


def run(ctx):
    docs = ctx['docs']
    os.makedirs(paths.OTHER_DIR, exist_ok=True)

    # 清理已移除条目的旧产物（gen_docs 只生成 DOCS 里登记的，不会自动删旧的）
    keep = {name + '.html' for name, _, _ in docs} | {'index.html'}
    stale = [f for f in os.listdir(paths.OTHER_DIR)
             if f.endswith('.html') and f not in keep]
    for f in stale:
        os.remove(os.path.join(paths.OTHER_DIR, f))
        print('  清理旧产物：other/' + f)

    # 已登记文档的站点根路径 → 输出文件名（互链重写用）
    doc_map = {'docs/%s.md' % name: '%s.html' % name for name, _, _ in docs}

    def rewrite(m):
        href = m.group(1)
        if re.match(r'^[a-z]+:', href) or href.startswith('#'):
            return m.group(0)
        if href in doc_map:
            return 'href="%s"' % doc_map[href]
        return 'href="../%s"' % href

    items = []
    for name, cat, blurb in docs:
        src_path = os.path.join(paths.DOCS_DIR, name + '.md')
        with open(src_path, encoding='utf-8') as f:
            text = f.read()
        title = mdlib.md_title(text) or name
        body = mdlib.md_to_html(text, prefix='docs/')
        body = re.sub(r'href="([^"]+)"', rewrite, body)
        out = PAGE_TMPL % {'title': html.escape(title), 'blurb': html.escape(blurb),
                           'name': name, 'body': body, 'css': CSS}
        with open(os.path.join(paths.OTHER_DIR, name + '.html'), 'w', encoding='utf-8') as f:
            f.write(out)
        items.append('<li><a href="%s.html"><b>%s<em>%s</em></b><span>%s</span></a></li>'
                     % (name, html.escape(title), html.escape(cat), html.escape(blurb)))

    index = INDEX_TMPL % {'css': CSS, 'items': '\n'.join(items), 'count': len(docs)}
    with open(os.path.join(paths.OTHER_DIR, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(index)
    print('  other/ 重写完：%d 篇文档 + 索引页' % len(docs))
