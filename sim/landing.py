#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""落点与移动学模拟（与规则版本无关）。

本脚本只关心「骰子 / 地图 / 落点分布」这些**没有被规则版本改动**的部分，
因此 v1/v2/v3 共用同一份——改名 landing.py（原 sim-v2.py）就是这个意思：
对局模拟在 game.py（随规则版本演进），落点模拟在这里。

口径：
  1. 骰子：1 枚十六面骰（1-16 等概率）。摇到 16 → 移动 16 格并结算，然后再摇一次；
     连续两次 16 → 移动结算后送进监狱 1 回合。
  2. 起点：**统一赤道 #0**，所有人同起点、同方向（顺时针前进）。
     （规则 v2 原文的「四角随机起点 + 单双定方向」是备选玩法，因为它会跟监狱冲突，
       本脚本按用户 2026-10-13 的确认走「赤道统一起点」这一支。）
  3. 地图：格子类型**不硬编码**，全部读 source/remix/map.json 的 variants.v2.replace —
     北极 #32 → 监狱、印度洋 #24 / 大西洋 #59 → 道具商店（太平洋 #10 仍是普通海洋格）。
  4. 监狱 = 北极 #32：被送进监狱时强制移动到这里，跳过若干回合，期间无法收租。
     送监狱来源：双 16、命运 1/4/13、机会 15（名下无房时）。
  5. 机会 / 命运牌：各 20 张；牌面含移动与坐牢效果（见 CHANCE / FATE）。
  6. 赤道 #0：每次经过奖励 2000。
  7. 过路费：空地 20% 地价；绿色 L 级 = 50% 地价 × L；红色 5 级 = 300% 地价。
     同颜色同归属连锁：总过路费 = 该色名下所有房屋过路费之和，向下取整十。
  8. 升级费：绿色每级 50% 地价；红色（4→5）100% 地价。

用法：python3 sim/landing.py
"""

import json
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_JSON = os.path.join(ROOT, "source", "remix", "map.json")

N_CELLS = 64
GO_CELL = 0             # 赤道：统一起点（v2 备选口径）
CORNERS = [0, 16, 32, 48]
# 起点口径："equator" = 统一赤道起点（默认，用户 2026-10-13 确认）；
#           "corners" = 四角随机起点 + 单双定方向（v2 原文的备选玩法，仅作对照）
START_MODE = "equator"

DICE_FACES = 16

START_CASH = 15000      # 备选 20000
GO_BONUS = 2000

# 机会牌里影响「移动 / 回合 / 坐牢」的
CHANCE_EXTRA_ROLL = {7, 14}       # 你骰子 +1
CHANCE_JAIL_IF_NO_HOUSE = {15}    # 名下无房 → 送进监狱 3 回合
# 命运牌：判定率 rate 为赢面，未赢即 lose
FATE = {
    1:  {"rate": 0.50, "lose": "jail3"},
    2:  {"rate": 0.50, "lose": "stay1"},
    3:  {"rate": 0.50},
    4:  {"rate": 0.50, "lose": "jail1"},
    5:  {"rate": 0.50},
    6:  {"rate": 0.50},
    7:  {"rate": 0.375},
    8:  {"rate": 0.1875},
    9:  {"rate": 0.9375},
    10: {"rate": 0.3125},
    11: {"rate": 0.50, "lose": "mute1"},
    12: {"rate": 0.50},
    13: {"rate": 0.25, "lose": "jail1"},
    14: {"rate": 0.50},
    15: {"rate": 0.50},
    16: {"rate": 0.50},
    17: {"rate": 0.50, "move": "parity"},
    18: {"rate": 0.50},
    19: {"rate": 0.50},
    20: {"rate": 0.50},
}
P_NO_HOUSE = 0.40            # 机会 15 时「名下无房」的概率
# 自然走到北极（#32）算不算坐牢？做成开关，默认 True（北极现在就是监狱格，
# 站上去自然要坐牢；v1 的备选读法是「只有被送进去才坐牢」）。
ARRIVE_JAIL_CELL_JAILS = True


def load_map():
    with open(MAP_JSON, encoding="utf-8") as f:
        return json.load(f)


def v2_replace(data):
    """JSON 里 variants.v2.replace：{格子 id: 要覆盖的字段}。"""
    var = (data.get("variants") or {}).get("v2") or {}
    return {int(k): v for k, v in (var.get("replace") or {}).items()}


def effective_tiles(data):
    """把 variants.v2 覆盖到格子上，得到「规则 v2 的棋盘」。"""
    patch = v2_replace(data)
    out = []
    for t in data["tiles"]:
        t = dict(t)
        t.update(patch.get(t["id"], {}))
        out.append(t)
    return out


_MEM = {}


def eff():
    """缓存：v2 棋盘 + 监狱格 / 商店格（都从 JSON 推，脚本里不写死）。"""
    if not _MEM:
        data = load_map()
        tiles = effective_tiles(data)
        _MEM["data"] = data
        _MEM["tiles"] = {t["id"]: t for t in tiles}
        _MEM["jail"] = next(t["id"] for t in tiles if t["type"] == "jail")
        _MEM["shops"] = sorted(t["id"] for t in tiles if t["type"] == "shop")
    return _MEM


def jail_cell():
    return eff()["jail"]


def shop_cells():
    return set(eff()["shops"])


def effective_average_step():
    """含「16 再摇」的每回合平均移动格数。"""
    s = sum(r / DICE_FACES for r in range(1, DICE_FACES))
    return (s + 1.0) / (1 - 1.0 / DICE_FACES)


def moves_per_turn():
    """含「16 再摇」的每回合平均落点（= 掷骰）次数。"""
    return 1.0 / (1 - 1.0 / DICE_FACES)


def probe_rolls(T):
    """解析推演：从 #0 出发、单向、每步 1d16 连走 T 步后的落点相对频率。

    只回答「统一的赤道起点会不会留下位置偏差」——不含 16 再摇、坐牢与卡牌移动。
    """
    st = [0.0] * N_CELLS
    st[0] = 1.0
    vis = [0.0] * N_CELLS
    p = [(r, 1.0 / DICE_FACES) for r in range(1, DICE_FACES + 1)]
    for _ in range(T):
        nx = [0.0] * N_CELLS
        for pos in range(N_CELLS):
            w = st[pos]
            if w <= 0:
                continue
            for r, pr in p:
                q = (pos + r) % N_CELLS
                vis[q] += w * pr
                nx[q] += w * pr
        st = nx
    avg = T / N_CELLS
    return [v / avg for v in vis]


class Sim:
    def __init__(self, rng):
        m = eff()
        data = m["data"]
        self.tiles = m["tiles"]
        self.jail = m["jail"]
        self.shops = m["shops"]
        self.rng = rng
        self.cells = [0] * N_CELLS
        self.arrive_jail = ARRIVE_JAIL_CELL_JAILS
        self.s = dict(landings=0, go_hits=0, distance=0, jail_total=0,
                      jail_double16=0, jail_card=0, jail_arrive=0,
                      sixteens=0, stayed=0, card_move=0, rolls=0, skips=0)

    def roll(self):
        self.s["rolls"] += 1
        return self.rng.randint(1, DICE_FACES)

    def move(self, pos, direction, r):
        """移动并结算落点，返回新位置。"""
        s = self.s
        new = (pos + r * direction) % N_CELLS
        passed = new == GO_CELL
        if not passed:
            if direction == 1:
                passed = new <= pos and r > 0 and pos != new
            else:
                passed = new >= pos and pos != 0
        if passed:
            s["go_hits"] += 1
        s["distance"] += r
        s["landings"] += 1
        self.cells[new] += 1
        return new

    def resolve(self, pos):
        """结算格子：返回 (新位置, 坐牢回合数)。"""
        tile = self.tiles[pos]
        if tile["type"] not in ("chance", "destiny"):
            return pos, 0
        idx = self.rng.randint(1, 20)
        s = self.s
        if tile["type"] == "chance":
            if idx in CHANCE_EXTRA_ROLL:
                s["card_extra"] = s.get("card_extra", 0) + 1
            elif idx in CHANCE_JAIL_IF_NO_HOUSE and self.rng.random() < P_NO_HOUSE:
                s["jail_card"] += 1
                return pos, 3
            return pos, 0
        spec = FATE[idx]
        lost = self.rng.random() >= spec.get("rate", 1.0)
        act = spec.get("lose") if lost else None
        if act == "jail1":
            s["jail_card"] += 1
            return pos, 1
        if act == "jail3":
            s["jail_card"] += 1
            return pos, 3
        if act == "stay1":
            s["stayed"] += 1
        if spec.get("move") == "parity":
            x = self.roll()
            if self.roll() % 2 == 1:
                pos = self.move(pos, 1, x)
            else:
                pos = self.move(pos, -1, x)
            s["card_move"] += 1
        return pos, 0

    def turn(self, pos, direction):
        """走一回合，返回 (新位置, 坐牢回合数)。"""
        s = self.s
        jail = 0
        streak = 0
        extra = 0
        s["card_extra"] = 0
        while True:
            r = self.roll()
            if r == DICE_FACES:
                s["sixteens"] += 1
                streak += 1
            else:
                streak = 0
            pos = self.move(pos, direction, r)
            pos, j = self.resolve(pos)
            jail = max(jail, j)
            if self.arrive_jail and pos == self.jail:
                s["jail_arrive"] += 1
                jail = max(jail, 1)
                break
            if r == DICE_FACES and streak >= 2:
                s["jail_double16"] += 1
                jail = max(jail, 1)
                break
            if r == DICE_FACES:
                continue
            extra += s.get("card_extra", 0)
            s["card_extra"] = 0
            if extra > 0:
                extra -= 1
                continue
            break
        if jail:
            pos = self.jail
        return pos, jail


def simulate(trials=400, players=8, turns=250, seed=20261013,
             arrive_jail=None, start=None):
    rng = random.Random(seed)
    sim = Sim(rng)
    if arrive_jail is not None:
        sim.arrive_jail = arrive_jail
    mode = start or START_MODE
    for _ in range(trials):
        for _p in range(players):
            if mode == "corners":            # 对照口径：四角随机 + 单双定方向
                first = sim.roll()
                pos = CORNERS[(first - 1) % 4]
                direction = 1 if first % 2 == 1 else -1
            else:                            # 默认口径：统一赤道起点、单向
                pos = GO_CELL
                direction = 1
            jail_left = 0
            for _t in range(turns):
                if jail_left > 0:
                    jail_left -= 1
                    sim.s["skips"] += 1
                    sim.s["jail_total"] += 1
                    continue
                pos, jail = sim.turn(pos, direction)
                if jail:
                    jail_left = jail - 1
                    sim.s["jail_total"] += 1
    return sim


def group_economy(share=None):
    """share: {格子 id: 一次落点落在该格的概率}；不给就按完全均匀假设。"""
    data = load_map()
    tiles = {t["id"]: t for t in data["tiles"]}
    mpt = moves_per_turn()
    rows = []
    for g in data["colorGroups"]:
        ids = sorted(t["id"] for t in data["tiles"] if t.get("colorId") == g["id"])
        total = sum(tiles[i]["price"] for i in ids)
        n = len(ids)
        segs = 1
        for a, b in zip(ids, ids[1:]):
            if b != a + 1:
                segs += 1
        freq = sum(share[i] for i in ids) if share else n / N_CELLS
        trigger = freq * mpt                 # 每个对手回合踩中该组任一格的概率
        rows.append(dict(
            name=g["name"], icon=g["icon"], n=n, segs=segs,
            avg=total / n, total=total, freq=freq,
            rent_max=3 * total, cost_max=4 * total,
            rent_land=0.2 * total, cost_land=total,
            trigger=trigger,
            exp_max=trigger * 3 * total,
            exp_land=trigger * 0.2 * total,
            pb_max=4 * total / (trigger * 3 * total),
            pb_land=total / (trigger * 0.2 * total),
        ))
    rows.sort(key=lambda r: -r["exp_max"])
    return rows


def main():
    print("=" * 84)
    print("规则 2 · 落点与收益模拟（1 枚十六面骰 · 统一赤道起点 · 连锁过路费）")
    print("=" * 84)
    m = eff()
    print(f"  棋盘：已套用 v2 变体 —— 监狱 #{m['jail']}（北极）· "
          f"道具商店 {m['shops']}（印度洋 / 大西洋）· 起点 #{GO_CELL}（赤道）")

    d, mpt = effective_average_step(), moves_per_turn()
    print("\n【一、移动学】")
    print(f"  每回合平均移动格数          {d:.4f} 格")
    print(f"  每回合平均落点（=掷骰）次数  {mpt:.4f} 次")
    print(f"  走完一圈平均需要            {N_CELLS / d:.2f} 个回合")
    print(f"  每回合经过赤道概率          {d / N_CELLS * 100:.2f}%"
          f"  → 期望 {d / N_CELLS * GO_BONUS:.0f} 元/回合 的固定收入")
    print(f"  （原版 2d6 对照：每回合平均 7 格、一圈 9.14 掷）")

    print("\n【二、统一起点带来的位置偏差】解析推演"
          "（从 #0 出发单向连走 T 步，不含 16 再摇 / 坐牢 / 卡牌）")
    print(f"  {'走多少步':>8}{'≈圈':>6}{'  最热格':>16}{'  最冷格':>16}{'极差':>8}{'触达不到':>10}")
    for T in (9, 18, 27, 45, 90, 250):
        rel2 = probe_rolls(T)
        hi = max(range(N_CELLS), key=lambda k: rel2[k])
        reach = [k for k in range(N_CELLS) if rel2[k] > 0]
        lo = min(reach, key=lambda k: rel2[k])
        print("  %8d%6.1f  %14s  %14s%7.2f×%8d 格"
              % (T, T / 9.14,
                 "#%d %s" % (hi, m["tiles"][hi]["name"]),
                 "#%d %s" % (lo, m["tiles"][lo]["name"]),
                 rel2[hi] / rel2[lo], N_CELLS - len(reach)))

    print("\n  对照：统一起点 vs 四角随机起点（同参数 8 人 × 250 回合 × 200 局）")
    for mode, label in (("equator", "统一赤道起点（现行）"),
                        ("corners", "四角随机 + 单双定方向")):
        sm = simulate(trials=200, start=mode)
        u = sm.s["landings"] / N_CELLS
        r4 = [sm.cells[k] / u for k in range(N_CELLS)]
        hi = max(range(N_CELLS), key=lambda k: r4[k])
        lo = min(range(N_CELLS), key=lambda k: r4[k])
        print(f"    {label:<24} 极差 {max(r4) / min(r4):.3f}×"
              f"   最热 #{hi} {sm.tiles[hi]['name']} {r4[hi]:.3f}×"
              f"   最冷 #{lo} {sm.tiles[lo]['name']} {r4[lo]:.3f}×")

    sim = simulate()
    s, cells = sim.s, sim.cells
    tot = s["landings"]
    uni = tot / N_CELLS
    rel = [cells[k] / uni for k in range(N_CELLS)]
    share = [cells[k] / tot for k in range(N_CELLS)]
    print(f"\n【三、落点分布实测】8 人 × 250 回合 × 400 局，共 {tot:,} 次落点")
    print(f"  完全均匀基准 = 1/64 = {1 / N_CELLS * 100:.4f}% / 落点   （{uni:,.0f} 次/格）")
    print(f"  实测极差 {max(rel) / min(rel):.3f}×（含坐牢与卡牌移动后的削弱效果）")
    print("  最热的 5 格：")
    for k in sorted(range(N_CELLS), key=lambda k: -rel[k])[:5]:
        print(f"    #{k:2d} {sim.tiles[k]['name']:6s} {rel[k]:.4f}×")
    print("  最冷的 5 格：")
    for k in sorted(range(N_CELLS), key=lambda k: rel[k])[:5]:
        print(f"    #{k:2d} {sim.tiles[k]['name']:6s} {rel[k]:.4f}×")

    print(f"\n  坐牢 {s['jail_total']:,} 次（双16 {s['jail_double16']:,} / "
          f"卡牌 {s['jail_card']:,} / 走到监狱 {s['jail_arrive']:,}）")
    events = s["jail_total"] - s["skips"]
    print(f"    → 实际坐牢事件 {events:,} 次、被跳过的回合 {s['skips']:,} 个")
    print(f"    → 每回合坐牢概率 {events / (s['landings'] / mpt) * 100:.2f}%，"
          f"平均每个玩家每 {1 / (events / (s['landings'] / mpt)) / (N_CELLS / d):.1f} 圈坐一次牢")
    print(f"  摇出 16 的次数 {s['sixteens']:,}（占掷骰 {s['sixteens'] / s['rolls'] * 100:.2f}%）")
    print(f"  卡牌造成的移动 {s['card_move']:,} 次（{s['card_move'] / tot * 100:.2f}%）")
    print(f"  原地停留 {s['stayed']:,} 次（{s['stayed'] / tot * 100:.2f}%）")
    print(f"  经过赤道 {s['go_hits']:,} 次 → 合计 {s['go_hits'] * GO_BONUS:,} 元，"
          f"平均 {s['go_hits'] * GO_BONUS / (s['rolls'] / mpt):.0f} 元/回合")

    print(f"\n  按组（该组每格的平均落点相对值，1.00× = 完全均匀）：")
    data = m["data"]
    out = []
    for g in data["colorGroups"]:
        ids = [t["id"] for t in data["tiles"] if t.get("colorId") == g["id"]]
        r2 = sum(rel[i] for i in ids) / len(ids)
        out.append((r2, g["icon"], g["name"], len(ids)))
    out.sort(reverse=True)
    for r2, ic, nm, n in out:
        print(f"    {ic} {nm:9s} n={n}  {r2:.4f}×")

    print("\n【三·补 口径 A/B】自然走到监狱格（北极 #%d）算不算坐牢？" % m["jail"])
    for aj in (False, True):
        sim2 = simulate(trials=200, players=8, turns=250, arrive_jail=aj)
        s2, c2 = sim2.s, sim2.cells
        u2 = s2["landings"] / N_CELLS
        ev = s2["jail_total"] - s2["skips"]
        tt = s2["landings"] / mpt
        r3 = [c2[k] / u2 for k in range(N_CELLS)]
        print(f"  {'走到即坐牢' if aj else '只有被送才坐牢':<14}"
              f"坐牢 {ev:>7,} 次（{ev / tt * 100:5.2f}%/回合 · "
              f"每 {1 / (ev / tt) / (N_CELLS / d):>4.1f} 圈 1 次）"
              f"   来源 双16 {s2['jail_double16']:>5,}"
              f" / 卡牌 {s2['jail_card']:>5,}"
              f" / 走到监狱 {s2['jail_arrive']:>6,}"
              f"   落点极差 {max(r3) / min(r3):.3f}×")

    print("\n【四、组经济（规则 2 连锁口径）】满级 = 5 级红房")
    hdr = (f"  {'组':<11}{'格':>3}{'段':>3}{'落点%':>7}{'均价':>7}{'总地价':>8}"
           f"{'满级连锁过路费':>14}{'满级投入':>10}"
           f"{'收益/对手回合':>14}{'回本圈':>8}")
    print(hdr)
    print("  " + "-" * 82)
    for r in group_economy(share):
        print(f"  {r['icon']}{r['name']:<10}{r['n']:>3}{r['segs']:>3}"
              f"{r['freq'] * 100:>6.2f}%{r['avg']:>7.0f}{r['total']:>8.0f}"
              f"{r['rent_max']:>14.0f}"
              f"{r['cost_max']:>10.0f}{r['exp_max']:>14.0f}"
              f"{r['pb_max'] / 7:>8.1f}")
    print("\n  只买空地不升级（0 级，过路费 20%）的回本圈数：")
    for r in group_economy(share):
        print(f"    {r['icon']}{r['name']:<10} {r['pb_land'] / 7:>5.1f} 圈")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "game":
        from game import main as game_main
        game_main()
    else:
        main()
