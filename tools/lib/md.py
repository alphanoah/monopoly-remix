"""简易 markdown → HTML（够规则文档 / 道具清单用：标题/列表/引用/表格/链接/粗体/行内码），
外加规则区的折叠小节工具。"""
import html
import re


def norm_href(p):
    """把 md 里「相对自身目录」的链接折叠成相对站点根的路径：source/../docs/x → docs/x。"""
    parts = []
    for seg in p.split('/'):
        if seg == '..':
            if parts:
                parts.pop()
        elif seg and seg != '.':
            parts.append(seg)
    return '/'.join(parts)


def strip_comments(text):
    """去掉独立成行的 HTML 注释（如 <!-- QUICK:START --> 标记），其余行原样保留。"""
    return '\n'.join(l for l in text.replace('\r\n', '\n').split('\n')
                     if not re.fullmatch(r'\s*<!--.*?-->\s*', l))


def inline(t, prefix='source/'):
    t = html.escape(t)
    t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'`(.+?)`', r'<code>\1</code>', t)
    t = re.sub(r'\[(.+?)\]\((?!https?:|#)(.+?)\)',
               lambda m: '<a href="%s">%s</a>' % (norm_href(prefix + m.group(2)), m.group(1)), t)
    t = re.sub(r'\[(.+?)\]\((https?:.+?)\)', r'<a href="\2">\1</a>', t)
    return t


def render_list(items, prefix):
    out, stack = [], []
    for lvl, ordered, text in items:
        tag = 'ol' if ordered else 'ul'
        while stack and stack[-1][0] > lvl:
            out.append('</li></%s>' % stack.pop()[1])
        if not stack:
            out.append('<%s>' % tag)
            stack.append((lvl, tag))
        else:
            top_lvl, top_tag = stack[-1]
            if lvl > top_lvl:
                out.append('<%s>' % tag)
                stack.append((lvl, tag))
            elif top_tag != tag:
                out.append('</li></%s>' % top_tag)
                stack.pop()
                out.append('<%s>' % tag)
                stack.append((lvl, tag))
            else:
                out.append('</li>')
        out.append('<li>' + inline(text, prefix))
    while stack:
        out.append('</li></%s>' % stack.pop()[1])
    return '\n'.join(out)


def render_table(lines, i, prefix):
    """解析 markdown 表格，返回 (html, 下一行下标)。首行必须是表头 + 分隔行。"""
    cells = lambda s: [c.strip() for c in s.strip().strip('|').split('|')]
    head = cells(lines[i])
    i += 2
    rows = []
    while i < len(lines) and lines[i].strip().startswith('|'):
        rows.append(cells(lines[i]))
        i += 1
    out = ['<div class="tw"><table>', '<thead><tr>' +
           ''.join('<th>%s</th>' % inline(c, prefix) for c in head) + '</tr></thead>', '<tbody>']
    for r in rows:
        out.append('<tr>' + ''.join('<td>%s</td>' % inline(c, prefix) for c in r) + '</tr>')
    out.append('</tbody></table></div>')
    return '\n'.join(out), i


def md_to_html(md, prefix='source/'):
    lines = md.replace('\r\n', '\n').split('\n')
    out, i = [], 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        if not line.strip():
            i += 1
            continue
        indent = len(line) - len(line.lstrip())
        s = line.strip()

        # 标题：# 是文件标题，首页已有大标题，跳过
        m = re.match(r'^(#{1,6})\s+(.*)', s)
        if m:
            lvl = len(m.group(1))
            if lvl >= 2:
                out.append('<h%d>%s</h%d>' % (min(lvl + 1, 6), inline(m.group(2), prefix), min(lvl + 1, 6)))
            i += 1
            continue

        # 表格（表头行 + |---| 分隔行）
        if s.startswith('|') and i + 1 < len(lines) and re.match(r'^\|[\s:|-]+\|$', lines[i + 1].strip()):
            tbl, i = render_table(lines, i, prefix)
            out.append(tbl)
            continue

        # 水平分隔线 --- / ***（首页用标题间距就够，直接跳过）
        if re.match(r'^(-{3,}|\*{3,}|_{3,})$', s):
            i += 1
            continue

        # 列表
        if re.match(r'^([-*+]|\d+[.)])\s+', s):
            items = []
            while i < len(lines):
                cur = lines[i].rstrip()
                if not cur.strip():
                    break
                ci = len(cur) - len(cur.lstrip())
                cs = cur.strip()
                mm = re.match(r'^(\d+[.)]|[-*+])\s+(.*)', cs)
                if not mm:
                    break
                items.append((ci // 2, bool(re.match(r'^\d', mm.group(1))), mm.group(2)))
                i += 1
            out.append(render_list(items, prefix))
            continue

        # 引用
        if s.startswith('>'):
            buf = []
            while i < len(lines) and lines[i].strip().startswith('>'):
                buf.append(lines[i].strip().lstrip('>').strip())
                i += 1
            out.append('<blockquote>%s</blockquote>' % '<br>'.join(inline(x, prefix) for x in buf))
            continue

        # 普通段落（连续行合并）
        buf = []
        while i < len(lines):
            cur = lines[i].rstrip()
            cs = cur.strip()
            if not cs or re.match(r'^(#{1,6})\s+', cs) or re.match(r'^([-*+]|\d+[.)])\s+', cs) or cs.startswith('>'):
                break
            buf.append(cs)
            i += 1
        if buf:
            out.append('<p>%s</p>' % '<br>'.join(inline(x, prefix) for x in buf))
    return '\n'.join(out)


def md_title(md):
    """取 md 的一级标题，没有就返回空字符串。"""
    m = re.search(r'^#\s+(.+?)\s*$', md, re.M)
    return m.group(1).strip() if m else ''


def strip_tags(s):
    """去掉行内标签，只留文字（折叠标题里常有 <code>【新版新增】</code> 这类标注）。"""
    return html.unescape(re.sub(r'<[^>]+>', '', s)).strip()


def fold(rules_html, level, keyword, to_end=False, title=None):
    """把标题含 keyword 的某一级小节折进 <details>，默认收起（原生折叠，不依赖 JS）。

    to_end=False 时只折到下一个同级/上级标题为止（用于「备选：北极监狱」这类可选小节）。
    """
    out = rules_html
    while True:
        m = re.search(r'<h%d>(.*?%s.*?)</h%d>' % (level, keyword, level), out)
        if not m:
            return out
        end = len(out)
        if not to_end:
            nxt = re.search(r'<h[34][ >]', out[m.end():])
            if nxt:
                end = m.end() + nxt.start()
        summary = title or strip_tags(m.group(1))
        out = ('%s<details class="fold"><summary>%s</summary>\n%s\n</details>\n%s'
               % (out[:m.start()], html.escape(summary), out[m.end():end], out[end:]))
