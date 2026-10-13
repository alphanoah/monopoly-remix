#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则 2 · 完整对局模拟（8 人混战，打到只剩一个）。

跟 sim-v2.py 的落点模拟不同，这里跑的是「一局完整游戏」：
买卖地产、升级房子、连锁收租、付不出钱就拍卖、破产退出。用来回答
「如果一组归你、另一组归他，谁更可能活到最后」。

【模型口径 / 简化说明】
  · 骰子、起点、监狱、赤道酬金完全按 content/new-rule.md（1 枚十六面骰）。
  · 过路费 / 升级费 / 连锁按规则 2；连锁只统计「同色且同归属」的房子。
  · 现金不够交过路费时按规则 2 拍卖：底价 = 已投入总额的 50%（向下取整十），
    你回收其中 75%（25% 上交银行）→ 实际只能拿回约 37.5%，卖完还不够 = 破产。
  · 破产：剩余现金与名下地产全部归债主。
  · **未建模**：道具买卖与使用、拍卖场上的玩家竞价（按底价成交）、玩家之间的
    讨价还价与交易、卡牌里少数只影响「下回合租金倍率/禁言」的效果。
    因此本模拟的绝对破产圈数偏乐观，但**组与组之间的相对排名是可信的**。
  · 8 名玩家各自锁定一个目标色组（政策相同），随机分配起点与方向。

用法：python3 tools/sim-v2.py game
"""

import json
import os
import random
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_JSON = os.path.join(ROOT, "content", "map-print-data.json")

N_CELLS = 64
JAIL_CELL = 32
GO_CELL = 0
CORNERS = [0, 16, 32, 48]
DICE_FACES = 16
GO_BONUS = 2000
START_CASH = 15000

# 命运牌判定率（rate = 赢面），移动/坐牢效果在 resolve_card 里按 idx 处理
FATE = {
    1: 0.50, 2: 0.50, 3: 0.50, 4: 0.50, 5: 0.50, 6: 0.50, 7: 0.375,
    8: 0.1875, 9: 0.9375, 10: 0.3125, 11: 0.50, 12: 0.50, 13: 0.25,
    14: 0.50, 15: 0.50, 16: 0.50, 17: 0.50, 18: 0.50, 19: 0.50, 20: 0.50,
}


def load_map():
    with open(MAP_JSON, encoding="utf-8") as f:
        return json.load(f)


BUY_BUFFER = 1000        # 买地后至少留这么多现金
UPGRADE_BUFFER = 2500    # 升级后至少留这么多现金
OPPORTUNISTIC_CASH = 5000   # 手头超过这个数才会顺手买非目标组的地
OPPORTUNISTIC_MAX_PRICE = 1200
AUCTION_RECOVERY = 0.375    # 拍卖实际回收比例（50% 底价 × 75% 归自己）


class Game:
    def __init__(self, rng, data, targets):
        self.rng = rng
        self.data = data
        self.tiles = {t["id"]: t for t in data["tiles"]}
        self.owner = [None] * N_CELLS      # 玩家编号
        self.level = [0] * N_CELLS         # 0..5
        self.players = []
        for i, gid in enumerate(targets):
            self.players.append(dict(
                idx=i, target=gid, cash=START_CASH, pos=0, direction=1,
                jail=0, extra=0, alive=True, laps=0.0,
            ))

    # ---------- 基础 ----------
    def roll(self):
        return self.rng.randint(1, DICE_FACES)

    def rent_of(self, cell):
        p = self.tiles[cell]["price"]
        lv = self.level[cell]
        if lv == 0:
            return 0.2 * p
        if lv <= 4:
            return 0.5 * p * lv
        return 3.0 * p

    def chain_rent(self, cell, owner):
        cid = self.tiles[cell]["colorId"]
        tot = 0.0
        for c in range(N_CELLS):
            if self.owner[c] == owner and self.tiles[c].get("colorId") == cid:
                tot += self.rent_of(c)
        return int(tot // 10 * 10)

    def invested(self, cell):
        p = self.tiles[cell]["price"]
        lv = self.level[cell]
        cost = p
        for step in range(1, lv + 1):
            cost += p * (1.0 if step == 5 else 0.5)
        return cost

    def upgrade_cost(self, cell):
        p = self.tiles[cell]["price"]
        return p * (1.0 if self.level[cell] == 4 else 0.5)

    # ---------- 交易 ----------
    def can_buy(self, pl, cell):
        t = self.tiles[cell]
        if self.owner[cell] is not None or "price" not in t:
            return False
        if pl["cash"] - t["price"] < BUY_BUFFER:
            return False
        if pl.get("spread"):          # 散布型：什么都买，不挑颜色
            return True
        if t.get("colorId") == pl["target"]:
            return True
        return (pl["cash"] > OPPORTUNISTIC_CASH
                and t["price"] <= OPPORTUNISTIC_MAX_PRICE)

    def best_upgrade(self, pl):
        if pl.get("spread"):
            cands = [c for c in range(N_CELLS)
                     if self.owner[c] == pl["idx"] and self.level[c] < 5]
        else:
            cands = [c for c in range(N_CELLS)
                     if self.owner[c] == pl["idx"]
                     and self.tiles[c].get("colorId") == pl["target"]
                     and self.level[c] < 5]
        if not cands:
            return None
        cands.sort(key=lambda c: -self.tiles[c]["price"])
        for c in cands:
            if pl["cash"] - self.upgrade_cost(c) >= UPGRADE_BUFFER:
                return c
        return None

    def liquidate(self, pl, need):
        """拍卖名下房产筹钱，返回实际筹到的现金。"""
        mine = [c for c in range(N_CELLS) if self.owner[c] == pl["idx"]]
        mine.sort(key=lambda c: (self.tiles[c].get("colorId") == pl["target"],
                                 self.tiles[c]["price"]))
        raised = 0.0
        for c in mine:
            if raised >= need:
                break
            raised += self.invested(c) * AUCTION_RECOVERY
            self.owner[c] = None
            self.level[c] = 0
        pl["cash"] += raised
        return raised

    def pay(self, pl, amount, to=None):
        """付款，付不出则拍卖、仍不够就破产。"""
        amount = int(amount)
        if pl["cash"] < amount:
            self.liquidate(pl, amount - pl["cash"])
        if pl["cash"] >= amount:
            pl["cash"] -= amount
            if to is not None:
                to["cash"] += amount
            return True
        paid = pl["cash"]
        pl["cash"] = 0
        if to is not None:
            to["cash"] += paid
        self.bankrupt(pl, to)
        return False

    def bankrupt(self, pl, creditor):
        pl["alive"] = False
        for c in range(N_CELLS):
            if self.owner[c] == pl["idx"]:
                if creditor is not None:
                    self.owner[c] = creditor["idx"]
                else:
                    self.owner[c] = None
                    self.level[c] = 0
        if creditor is not None:
            creditor["cash"] += pl["cash"]
        pl["cash"] = 0

    def move(self, pl, r):
        new = (pl["pos"] + r * pl["direction"]) % N_CELLS
        passed = new == GO_CELL
        if not passed:
            if pl["direction"] == 1:
                passed = new <= pl["pos"] and pl["pos"] != new
            else:
                passed = new >= pl["pos"] and pl["pos"] != 0
        if passed:
            pl["cash"] += GO_BONUS
            pl["laps"] += 1
        pl["pos"] = new
        return self.resolve(pl)

    # ---------- 卡牌 ----------
    def resolve(self, pl):
        t = self.tiles[pl["pos"]]
        if t["type"] == "property":
            self.resolve_property(pl)
        elif t["type"] in ("chance", "destiny"):
            self.resolve_card(pl, t["type"])
        return 0

    def resolve_property(self, pl):
        cell = pl["pos"]
        owner = self.owner[cell]
        if owner is None:
            if self.can_buy(pl, cell):
                price = self.tiles[cell]["price"]
                pl["cash"] -= price
                self.owner[cell] = pl["idx"]
                self.level[cell] = 0
            return
        if owner == pl["idx"]:
            c = self.best_upgrade(pl)
            if c is not None:
                pl["cash"] -= self.upgrade_cost(c)
                self.level[c] += 1
            return
        other = self.players[owner]
        if not other["alive"]:
            return
        rent = self.chain_rent(cell, owner)
        self.pay(pl, rent, other)

    def richest(self, exclude=None):
        pool = [p for p in self.players if p["alive"] and p is not exclude]
        return max(pool, key=lambda p: p["cash"]) if pool else None

    def resolve_card(self, pl, kind):
        rng = self.rng
        if kind == "chance":
            idx = rng.randint(1, 20)
        else:
            idx = rng.randint(1, 20)
        if kind == "chance":
            if idx == 1:
                r = self.richest()
                if r is not None:
                    self.pay(r, 2000)
                    if r is not pl:
                        pl["cash"] += 2000
            elif idx == 2:
                r = self.richest(exclude=pl)
                if r is not None:
                    self.pay(r, 1000, pl)
            elif idx == 3:
                pl["cash"] += 3000
                l = self.players[(pl["idx"] - 1) % len(self.players)]
                if l["alive"]:
                    self.pay(l, 1000)
            elif idx == 4:
                pl["cash"] += 1000
            elif idx == 5:
                pl["cash"] += 1500
            elif idx == 6:
                pl["cash"] += 2500
            elif idx == 7:
                pl["extra"] += 1
            elif idx == 8:
                r = self.richest(exclude=pl)
                if r is not None:
                    mine = [c for c in range(N_CELLS) if self.owner[c] == r["idx"]]
                    if mine:
                        c = max(mine, key=lambda x: self.tiles[x]["price"])
                        r["cash"] += self.invested(c) * AUCTION_RECOVERY
                        self.owner[c] = None
                        self.level[c] = 0
            elif idx == 9:
                pl["cash"] += 1000
            elif idx == 10:
                mine = [c for c in range(N_CELLS)
                        if self.owner[c] == pl["idx"] and self.level[c] > 0]
                if mine:
                    c = max(mine, key=lambda x: self.tiles[x]["price"])
                    self.level[c] -= 1
                pl["cash"] += 1500
            elif idx == 11:
                jailed = [p for p in self.players if p["alive"] and p["jail"] > 0
                          and p is not pl]
                for p in jailed:
                    self.pay(p, 300, pl)
            elif idx == 12:
                others = [p for p in self.players
                          if p["alive"] and p is not pl]
                for p in others[:2]:
                    self.pay(p, 1000, pl)
            elif idx == 13:
                for p in self.players:
                    if p["alive"] and p is not pl:
                        self.pay(p, 200, pl)
            elif idx == 14:
                pl["extra"] += 1
            elif idx == 15:
                mine = [c for c in range(N_CELLS) if self.owner[c] == pl["idx"]]
                if mine:
                    c = max(mine, key=lambda x: self.tiles[x]["price"])
                    self.level[c] = 0
                    self.owner[c] = None
                else:
                    pl["jail"] = 3
            elif idx == 16:
                pl["cash"] -= 1500
            elif idx == 17:
                pl["cash"] -= 500
            elif idx == 18:
                pl["cash"] -= 1000
            elif idx == 19:
                pl["cash"] -= 2500
            elif idx == 20:
                for p in self.players:
                    if p["alive"] and p is not pl:
                        self.pay(pl, 200, p)
            if pl["cash"] < 0:
                self.pay(pl, -pl["cash"])
            return
        win = rng.random() < FATE[idx]
        if idx == 1:
            if win:
                pl["cash"] += 3000
            else:
                pl["jail"] = 3
        elif idx == 2:
            pl["cash"] += 3000 if win else 0
            if not win:
                pl["cash"] -= 2000
        elif idx == 3:
            pl["cash"] += 2000 if win else -2000
        elif idx == 4:
            if win:
                pl["cash"] += 1000
            else:
                pl["jail"] = 1
        elif idx == 6:
            pl["cash"] += 1500 if win else -1500
        elif idx == 7:
            pl["cash"] += 1600 if win else -1000
        elif idx == 8:
            pl["cash"] += 2600 if win else -600
        elif idx == 9:
            pl["cash"] += 200 if win else -3000
        elif idx == 10:
            pl["cash"] += 2200 if win else -1000
        elif idx == 11:
            pl["cash"] += 800 if win else 0
        elif idx == 12:
            pl["cash"] += 3000 if win else -3000
        elif idx == 13:
            if win:
                pl["cash"] += 3000
            else:
                pl["jail"] = 1
        elif idx == 14:
            if win:
                pl["cash"] += 1000
            else:
                mine = [c for c in range(N_CELLS)
                        if self.owner[c] == pl["idx"] and self.level[c] > 0]
                if mine:
                    c = max(mine, key=lambda x: self.tiles[x]["price"])
                    self.level[c] -= 1
        elif idx == 16:
            mine = [c for c in range(N_CELLS) if self.owner[c] == pl["idx"]]
            if mine:
                c = max(mine, key=lambda x: self.tiles[x]["price"])
                pl["cash"] += self.invested(c)
                self.owner[c] = None
                self.level[c] = 0
        elif idx == 17:
            x = self.roll()
            d = 1 if self.roll() % 2 == 1 else -1
            pl["pos"] = (pl["pos"] + x * d) % N_CELLS
            self.resolve(pl)
        elif idx == 18:
            others = [p for p in self.players if p["alive"] and p is not pl]
            if others:
                v = max(1, int(others[rng.randrange(len(others))]["cash"] * 0.2 // 10 * 10))
                tgt = others[rng.randrange(len(others))]
                if win:
                    self.pay(tgt, v, pl)
                else:
                    self.pay(pl, v, tgt)
        elif idx == 19:
            pl["cash"] += (self.roll() * 200 - 1600) if win else -800
        if pl["cash"] < 0:
            self.pay(pl, -pl["cash"])

    # ---------- 一回合 ----------
    def turn(self, pl):
        if pl["jail"] > 0:
            pl["jail"] -= 1
            return
        streak = 0
        while True:
            r = self.roll()
            streak = streak + 1 if r == DICE_FACES else 0
            self.move(pl, r)
            if not pl["alive"]:
                return
            if pl["jail"] > 0:
                pl["pos"] = JAIL_CELL
                return
            if r == DICE_FACES and streak >= 2:
                pl["jail"] = 1
                pl["pos"] = JAIL_CELL
                return
            if r == DICE_FACES:
                continue
            if pl["extra"] > 0:
                pl["extra"] -= 1
                continue
            return


def run_game(rng, data, targets, max_rounds=600):
    g = Game(rng, data, targets)
    for i, pl in enumerate(g.players):
        first = g.roll()
        pl["pos"] = CORNERS[(first - 1) % 4]
        pl["direction"] = 1 if first % 2 == 1 else -1
    rounds_used = max_rounds
    for rd in range(max_rounds):
        alive = [p for p in g.players if p["alive"]]
        if len(alive) <= 1:
            rounds_used = rd
            break
        for pl in list(g.players):
            if pl["alive"]:
                g.turn(pl)
    alive = [p for p in g.players if p["alive"]]
    if len(alive) == 1:
        return alive[0], g, rounds_used, True
    return max(alive, key=lambda p: p["cash"]), g, rounds_used, False


def main():
    if os.environ.get("COHORT"):
        cohort_main()
        return
    trials = int(os.environ.get("TRIALS", "400"))
    data = load_map()
    groups = {g["id"]: g for g in data["colorGroups"]}
    tiles = {t["id"]: t for t in data["tiles"]}
    # 按「格数 × 总地价」给组排序，前 8 名分配给 8 个玩家
    score = []
    for gid, g in groups.items():
        ids = [t["id"] for t in data["tiles"] if t.get("colorId") == gid]
        total = sum(tiles[i]["price"] for i in ids)
        score.append((len(ids) * total, gid))
    score.sort(reverse=True)
    order = [gid for _, gid in score][:8]

    rng = random.Random(424242)
    wins = Counter()
    rounds = []
    ended = []
    for _ in range(trials):
        targets = order[:]
        rng.shuffle(targets)
        winner, g, r, settled = run_game(rng, data, targets)
        wins[winner["target"]] += 1
        rounds.append(r)
        ended.append(settled)

    print("=" * 76)
    print(f"规则 2 · 完整对局模拟：8 人混战 × {trials} 局（各自锁定一个目标色组）")
    print("=" * 76)
    print("\n  只有前 8 名的组会被分配玩家，所以下面只列这 8 个组\n")
    print("  组                格  段  总地价   满级连锁  夺冠次数   胜率")
    rows = []
    for gid in order:
        ids = sorted(t["id"] for t in data["tiles"] if t.get("colorId") == gid)
        total = sum(tiles[i]["price"] for i in ids)
        segs = 1
        for a, b in zip(ids, ids[1:]):
            if b != a + 1:
                segs += 1
        g = groups[gid]
        rows.append((wins[gid], gid, len(ids), segs, total, g["icon"], g["name"]))
    rows.sort(reverse=True)
    for w, gid, n, segs, total, ic, nm in rows:
        print(f"  {ic}{nm:<11}{n:>3}{segs:>4}{total:>8}{3 * total:>10}"
              f"{w:>8}   {w / trials * 100:>5.1f}%")
    print(f"\n  平均分出胜负用了 {sum(rounds) / len(rounds):.0f} 个回合"
          f"（约 {sum(rounds) / len(rounds) / 7.06:.0f} 圈/人）")
    print(f"  真正打到只剩一人的比例：{sum(ended) / len(ended) * 100:.1f}%"
          f"（其余按现金判胜）")


def cohort_main():
    """A/B：4 名「集中同色」玩家 vs 4 名「到处撒」玩家。"""
    trials = int(os.environ.get("TRIALS", "600"))
    data = load_map()
    tiles = {t["id"]: t for t in data["tiles"]}
    score = []
    for g in data["colorGroups"]:
        ids = [t["id"] for t in data["tiles"] if t.get("colorId") == g["id"]]
        score.append((len(ids) * sum(tiles[i]["price"] for i in ids), g["id"]))
    score.sort(reverse=True)
    order = [gid for _, gid in score]
    rng = random.Random(20261013)
    conc_wins = 0
    spread_wins = 0
    rounds = []
    alive_conc = 0
    for _ in range(trials):
        targets = [order[i % len(order)] for i in range(4)]
        g = Game(rng, data, targets)
        for i, pl in enumerate(g.players):
            pl["spread"] = i >= 4
        for pl in g.players:
            first = g.roll()
            pl["pos"] = CORNERS[(first - 1) % 4]
            pl["direction"] = 1 if first % 2 == 1 else -1
        used = 600
        for rd in range(600):
            if sum(1 for p in g.players if p["alive"]) <= 1:
                used = rd
                break
            for pl in list(g.players):
                if pl["alive"]:
                    g.turn(pl)
        alive = [p for p in g.players if p["alive"]]
        rounds.append(used)
        alive_conc += sum(1 for p in alive if not p.get("spread"))
        if alive:
            w = max(alive, key=lambda p: p["cash"])
            if w.get("spread"):
                spread_wins += 1
            else:
                conc_wins += 1
    print("=" * 70)
    print(f"规则 2 · A/B 对照：4 名「集中同色」vs 4 名「到处撒」× {trials} 局")
    print("=" * 70)
    print("\n  两类玩家打法完全相同，唯一区别是「买不买同一个颜色」：")
    print("  都买地、都升级、都会连锁判租，撒开的人只是每块地颜色都不同。\n")
    print(f"  集中同色获胜：{conc_wins:>4} 局  ({conc_wins / trials * 100:.1f}%)")
    print(f"  到处撒获胜  ：{spread_wins:>4} 局  ({spread_wins / trials * 100:.1f}%)")
    print(f"\n  平均分出胜负用 {sum(rounds) / len(rounds):.0f} 个回合"
          f"（约 {sum(rounds) / len(rounds) / 7.06:.0f} 圈/人）")
    print(f"  平均活到最后的集中型玩家数：{alive_conc / trials:.2f} / 4")


if __name__ == "__main__":
    main()

