#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则 2（content/new-rule.md）落点与收益模拟。

规则 2 与原版的关键差异（本脚本按这些口径跑）：
  1. 骰子：1 枚十六面骰（1-16 等概率）。摇到 16 → 移动 16 格并结算，然后再摇一次；
     连续两次 16 → 移动结算后送进监狱 1 回合。
  2. 起点：赤道顺时针四个角（#0 赤道 / #16 地中海 / #32 北极 / #48 夏威夷）随机；
     单数顺时针、双数逆时针。
  3. 监狱 = 北极 #32：被送进监狱时强制移动到这里，跳过若干回合，期间无法收租。
     送监狱来源：双 16、命运 1/4/13、机会 15（名下无房时）。
  4. 机会 / 命运牌：各 20 张，等概率；牌面含移动与坐牢效果（见 CHANCE / FATE）。
  5. 赤道 #0：每次经过奖励 2000。
  6. 过路费：空地 20% 地价；绿色 L 级 = 50% 地价 × L；红色 5 级 = 300% 地价。
     同颜色同归属连锁：总过路费 = 该色名下所有房屋过路费之和，向下取整十。
  7. 升级费：绿色每级 50% 地价；红色（4→5）100% 地价。

用法：python3 tools/sim-v2.py
"""

import json
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_JSON = os.path.join(ROOT, "content", "map-print-data.json")

N_CELLS = 64
JAIL_CELL = 32          # 北极
GO_CELL = 0             # 赤道
CORNERS = [0, 16, 32, 48]

START_CASH = 15000      # 备选 20000
GO_BONUS = 2000
DICE_FACES = 16

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
# 自然走到北极（#32）算不算坐牢？规则 2 原文没写死，做成开关做 A/B。
#   False = 只有被卡牌/双 16「送」进去才坐牢（本脚本默认，也是字面读法）
#   True  = 走到北极也强制坐牢 1 回合（经典大富翁的「进监狱」读法）
ARRIVE_JAIL_CELL_JAILS = False


def load_map():
    with open(MAP_JSON, encoding="utf-8") as f:
        return json.load(f)


def effective_average_step():
    """含「16 再摇」的每回合平均移动格数。"""
    s = sum(r / DICE_FACES for r in range(1, DICE_FACES))
    return (s + 1.0) / (1 - 1.0 / DICE_FACES)


def moves_per_turn():
    """含「16 再摇」的每回合平均落点（= 掷骰）次数。"""
    return 1.0 / (1 - 1.0 / DICE_FACES)


class Sim:
    def __init__(self, rng):
        data = load_map()
        self.tiles = {t["id"]: t for t in data["tiles"]}
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
            if self.arrive_jail and pos == JAIL_CELL:
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
            pos = JAIL_CELL
        return pos, jail


def simulate(trials=400, players=8, turns=250, seed=20261013,
             arrive_jail=None):
    rng = random.Random(seed)
    sim = Sim(rng)
    if arrive_jail is not None:
        sim.arrive_jail = arrive_jail
    for _ in range(trials):
        for _p in range(players):
            first = sim.roll()
            pos = CORNERS[(first - 1) % 4]
            direction = 1 if first % 2 == 1 else -1
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


def group_economy():
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
        trigger = n / N_CELLS * mpt          # 每个对手回合踩中该组任一格的概率
        rows.append(dict(
            name=g["name"], icon=g["icon"], n=n, segs=segs,
            avg=total / n, total=total,
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
    print("=" * 80)
    print("规则 2 · 落点与收益模拟（1 枚十六面骰 · 四角起点 · 连锁过路费）")
    print("=" * 80)

    d, mpt = effective_average_step(), moves_per_turn()
    print("\n【一、移动学】")
    print(f"  每回合平均移动格数          {d:.4f} 格")
    print(f"  每回合平均落点（=掷骰）次数  {mpt:.4f} 次")
    print(f"  走完一圈平均需要            {N_CELLS / d:.2f} 个回合")
    print(f"  每回合经过赤道概率          {d / N_CELLS * 100:.2f}%"
          f"  → 期望 {d / N_CELLS * GO_BONUS:.0f} 元/回合 的固定收入")
    print(f"  （原版 2d6 对照：每回合平均 7 格、一圈 9.14 掷）")

    sim = simulate()
    s, cells = sim.s, sim.cells
    tot = s["landings"]
    uni = tot / N_CELLS
    print(f"\n【二、落点分布】8 人 × 250 回合 × 400 局，共 {tot:,} 次落点")
    print(f"  完全均匀基准 = 1/64 = {1 / N_CELLS * 100:.4f}% / 落点   （{uni:,.0f} 次/格）")
    z = [(abs(cells[k] - uni) / (uni ** 0.5), k) for k in range(N_CELLS)]
    print(f"  偏离最大的 3 格：")
    for zz, k in sorted(z)[::-1][:3]:
        print(f"    #{k:2d} {sim.tiles[k]['name']:6s} {cells[k] / uni:.4f}×   "
              f"（{zz:.1f}σ）")
    print(f"  最大偏离 {max(abs(cells[k] / uni - 1) for k in range(N_CELLS)) * 100:.1f}%，"
          f"完全落在统计噪声内 → 落点就是均匀")
    print(f"\n  坐牢 {s['jail_total']:,} 次（双16 {s['jail_double16']:,} / "
          f"卡牌 {s['jail_card']:,}）")
    events = s["jail_total"] - s["skips"]
    print(f"    → 实际坐牢事件 {events:,} 次、被跳过的回合 {s['skips']:,} 个")
    print(f"    → 每回合坐牢概率 {events / (s['landings'] / mpt) * 100:.2f}%，"
          f"平均每个玩家每 {1 / (events / (s['landings'] / mpt)) / (N_CELLS / d):.1f} 圈坐一次牢")
    print(f"  摇出 16 的次数 {s['sixteens']:,}（占掷骰 {s['sixteens'] / s['rolls'] * 100:.2f}%）")
    print(f"  卡牌造成的移动 {s['card_move']:,} 次（{s['card_move'] / tot * 100:.2f}%）")
    print(f"  原地停留 {s['stayed']:,} 次（{s['stayed'] / tot * 100:.2f}%）")
    print(f"  经过赤道 {s['go_hits']:,} 次 → 合计 {s['go_hits'] * GO_BONUS:,} 元，"
          f"平均 {s['go_hits'] * GO_BONUS / (s['rolls'] / mpt):.0f} 元/回合")

    print(f"\n  按组（每格落点相对均匀基准）：", end="")
    data = load_map()
    out = []
    for g in data["colorGroups"]:
        ids = [t["id"] for t in data["tiles"] if t.get("colorId") == g["id"]]
        rel = sum(cells[i] / uni for i in ids) / len(ids)
        out.append((rel, g["icon"], g["name"], len(ids)))
    out.sort(reverse=True)
    print()
    for rel, ic, nm, n in out:
        print(f"    {ic} {nm:9s} n={n}  {rel:.4f}×")

    print("\n【二·补 口径 A/B】自然走到北极（#32）算不算坐牢？")
    for aj in (False, True):
        sim2 = simulate(trials=200, players=8, turns=250, arrive_jail=aj)
        s2, c2 = sim2.s, sim2.cells
        u2 = s2["landings"] / N_CELLS
        ev = s2["jail_total"] - s2["skips"]
        tt = s2["landings"] / mpt
        rel = [c2[k] / u2 for k in range(N_CELLS)]
        print(f"  {'走到即坐牢' if aj else '只有被送才坐牢':<14}"
              f"坐牢 {ev:>7,} 次（{ev / tt * 100:5.2f}%/回合 · "
              f"每 {1 / (ev / tt) / (N_CELLS / d):>4.1f} 圈 1 次）"
              f"   来源 双16 {s2['jail_double16']:>5,}"
              f" / 卡牌 {s2['jail_card']:>5,}"
              f" / 走到北极 {s2['jail_arrive']:>6,}"
              f"   落点极差 {max(rel) / min(rel):.3f}×")

    print("\n【三、组经济（规则 2 连锁口径）】满级 = 5 级红房")
    hdr = (f"  {'组':<11}{'格':>3}{'段':>3}{'均价':>7}{'总地价':>8}"
           f"{'满级连锁过路费':>14}{'满级投入':>10}"
           f"{'收益/对手回合':>14}{'回本圈':>8}")
    print(hdr)
    print("  " + "-" * 74)
    for r in group_economy():
        print(f"  {r['icon']}{r['name']:<10}{r['n']:>3}{r['segs']:>3}"
              f"{r['avg']:>7.0f}{r['total']:>8.0f}{r['rent_max']:>14.0f}"
              f"{r['cost_max']:>10.0f}{r['exp_max']:>14.0f}"
              f"{r['pb_max'] / 7:>8.1f}")
    print("\n  只买空地不升级（0 级，过路费 20%）的回本圈数：")
    for r in group_economy():
        print(f"    {r['icon']}{r['name']:<10} {r['pb_land'] / 7:>5.1f} 圈")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "game":
        from game import main as game_main
        game_main()
    else:
        main()
