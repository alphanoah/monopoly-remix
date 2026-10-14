"""标记块替换：生成物只写 `MARKER:START` / `MARKER:END` 包住的区域，其余手改部分不动。"""
import os
import re


def swap(path, pattern, block, label):
    if not os.path.exists(path):
        print('  跳过：未找到 %s' % path)
        return False
    with open(path, encoding='utf-8') as f:
        txt = f.read()
    new, n = re.subn(pattern, lambda m: block, txt, flags=re.S)
    if n != 1:
        print('  !! %s 里的标记块不是唯一（找到 %d 处），已跳过 %s' % (path, n, label))
        return False
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new)
    return True


def apply_blocks(path, blocks, ctx):
    """按站点地图依次重写一个页面的各标记块。

    blocks = [(标记名, 生成器)]；生成器返回 (pattern, block, 成功时的打印语) 或 None（本块跳过）。
    """
    for marker, gen in blocks:
        r = gen(ctx)
        if r is None:
            continue
        pattern, block, report = r
        if swap(path, pattern, block, marker):
            print('  ' + report)
