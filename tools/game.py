#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则 2 · 完整对局模拟（8 人混战，打到只剩一个）。

跟 sim-v2.py 的落点模拟不同，这里跑的是「一局完整游戏」：
买卖地产、升级房子、连锁收租、付不出钱就拍卖、破产退出。用来回答
「如果一组归你、另一组归他，谁更可能活到最后」。

【模型口径 / 简化说明】
  · 骰子、起点、监狱、赤道酬金完全按 content/new-rule.md（1 枚十六面骰）。
    摇到 16 → 移动并结算后再摇一次；同一回合内连续两次 16 → 送进监狱 1 回合。
  · 过路费 / 升级费 / 连锁按规则 2；连锁只统计「同色且同归属」的房子。
  · 现金不够交过路费时按规则 2 拍卖：底价 = 已投入总额的 50%（向下取整十），
    你回收其中 75%（25% 上交银行）→ 实际只能拿回约 37.5%，卖完还不够 = 破产。
  · 破产：剩余现金与名下地产全部归债主。
  · **卡牌已全量建模**：v7 的 20 张机会 + 20 张命运，含金钱、移动、坐牢、
    原地停留、禁言、下回合租金/过路费倍率、单双限行、与前方玩家对决等；
    条件牌的赢面直接用 cards.csv 的 rate。
  · **道具已建模 14 种**：商店 = 三个海洋格（#10/#24/#59）——地图 64 格里没有
    商店格，这是本脚本的假设，改 SHOP_CELLS 即可换口径。AI 只在「有确定性收益」
    时买与用（遥控骰子推进自家地、工程机器人免费升级、导弹降级对手满级房…）。
  · **未建模**：路障（无效果）、拍卖场上的玩家竞价（按底价成交）、玩家之间的
    讨价还价与交易。因此本模拟的绝对破产圈数偏乐观，但**组与组之间的相对排名可信**。
  · 8 名玩家各自锁定一个目标色组（政策相同），随机分配起点与方向。

用法：
  python3 tools/game.py               # 单配置：8 人各锁一组
  AB=1 python3 tools/game.py          # 2×2 对照：道具 × 北极坐牢
  COHORT=1 python3 tools/game.py      # A/B：集中同色 vs 到处撒
  TRIALS=250 python3 tools/game.py    # 每个配置跑多少局（默认 400 / AB 默认 200）
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

# 机会 12「欧洲区域玩家每人付你 1000」的判定集合（俄罗斯/波兰/德国/奥地利/瑞士/法国/
# 比利时/荷兰/英国/芬兰/瑞典/丹麦/希腊/意大利/西班牙/葡萄牙）
EUROPE_CELLS = {21, 22, 23, 25, 26, 27, 28, 30, 31, 33, 34, 35, 36, 37, 39, 40}

# ==================== 道具系统 ====================
# ⚠️ 商店格口径：地图 64 格里没有专门的「商店」格，这里把三个**海洋格**当作商店
#    （太平洋 #10 / 印度洋 #24 / 大西洋 #59）——理由是它们目前是唯一「走上去什么都不
#    发生」的功能空缺格，且均匀分布在四条边上。若你们另有约定，改 SHOP_CELLS 即可。
SHOP_CELLS = {10, 24, 59}
PROPS = {
    "乌龟帽": 1000, "工程机器人": 2000, "导弹": 2000, "遥控骰子": 1000,
    "路障": 500, "嫁祸卡": 1000, "免责卡": 1000, "汽车": 1000,
    "冷冻枪": 1000, "抢夺卡": 1000, "转向卡": 1000, "绿卡": 1500,
    "红卡": 1500, "拍卖卡": 2000,
}
PROP_RESERVE = 3000     # 买道具后至少留这么多现金
MAX_PROPS = 3           # 每人最多同时持有 3 件（规则只说「进入商店可半价出售」，未限上限）
RED_CARD_MIN = 3000     # 单次收租 ≥ 这个数才舍得用红卡
GREEN_CARD_MIN = 3000   # 单次付款 ≥ 这个数才舍得用绿卡
PROPS_ENABLED = True    # 道具总开关（跑 A/B 用）
ARRIVE_JAIL_CELL_JAILS = False   # 自然走到北极（#32）是否也算坐牢


class Game:
    def __init__(self, rng, data, targets):
        self.rng = rng
        self.data = data
        self.tiles = {t["id"]: t for t in data["tiles"]}
        self.owner = [None] * N_CELLS      # 玩家编号
        self.level = [0] * N_CELLS         # 0..5
        self.limit_parity = False          # 命运 15：下一回合单数原地停留
        self.props_enabled = PROPS_ENABLED
        self.arrive_jail = ARRIVE_JAIL_CELL_JAILS
        self.shop_visits = 0
        self.props_bought = 0
        self.shop_stock = {}               # 本店刷新出来的道具（全局共用一副牌堆）
        self.players = []
        for i, gid in enumerate(targets):
            self.players.append(dict(
                idx=i, target=gid, cash=START_CASH, pos=0, direction=1,
                jail=0, extra=0, alive=True, laps=0.0,
                spread=False,
                # —— 卡牌挂起的「下一回合生效」状态 ——
                rent_mult=1.0, rent_pending=1.0,   # 收租倍率（命运 5）
                toll_mult=1.0, toll_pending=1.0,   # 应付过路费倍率（机会 18）
                mute=False, mute_pending=False,    # 禁言（命运 11）
                stay=0,                            # 原地停留剩余回合（机会 4/7、命运 2）
                # —— 道具相关 ——
                props=[],                          # 持有道具名（列表，可重复）
                double_move=False,                 # 汽车：下次移动双倍
                slow=0,                            # 乌龟帽：剩余回合只能走 1 格
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
        if pl["mute"]:                       # 命运 11：禁言回合不能买/升级
            return False
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
        if pl["mute"]:
            return None
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

    def pay(self, pl, amount, to=None, is_rent=False):
        """付款，付不出则拍卖、仍不够就破产。"""
        amount = int(amount)
        if is_rent and amount >= GREEN_CARD_MIN and "绿卡" in pl["props"]:
            pl["props"].remove("绿卡")      # 绿卡：抵消一次付款
            return True
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
        elif self.props_enabled and pl["pos"] in SHOP_CELLS:
            self.shop_visit(pl)
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
        # 机会 18（付方翻倍）× 命运 5（收方翻倍/减半）
        rent = self.chain_rent(cell, owner) * pl["toll_mult"] * other["rent_mult"]
        if rent >= RED_CARD_MIN and "红卡" in other["props"]:
            other["props"].remove("红卡")   # 红卡：让这一次收款翻倍
            rent *= 2
        self.pay(pl, rent, other, is_rent=True)

    def richest(self, exclude=None):
        pool = [p for p in self.players if p["alive"] and p is not exclude]
        return max(pool, key=lambda p: p["cash"]) if pool else None

    def ahead(self, pl, k=1):
        """沿该玩家前进方向，找前方第 k 个玩家（1 = 最近）。"""
        alive = [p for p in self.players if p["alive"] and p is not pl]
        if not alive:
            return None
        d = pl["direction"]
        alive.sort(key=lambda p: ((p["pos"] - pl["pos"]) * d) % N_CELLS)
        return alive[(k - 1) % len(alive)]

    def resolve_card(self, pl, kind):
        rng = self.rng
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
                tgt = self.ahead(pl)          # 前方最近棋子原地停留一回合
                if tgt is not None:
                    tgt["stay"] = max(tgt["stay"], 1)
            elif idx == 5:
                pl["cash"] += 1500
            elif idx == 6:
                pl["cash"] += 2500
            elif idx == 7:
                pl["extra"] += 1              # 骰子 +1（多走一次）
                tgt = self.players[(pl["idx"] + 1) % len(self.players)]
                if tgt["alive"]:              # 右手玩家原地停留一回合
                    tgt["stay"] = max(tgt["stay"], 1)
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
                # 欧洲区域玩家每人付你 1000：按「持有 ≥2 块欧洲地产」判定
                for p in self.players:
                    if not p["alive"] or p is pl:
                        continue
                    eu = sum(1 for c in range(N_CELLS)
                             if self.owner[c] == p["idx"] and c in EUROPE_CELLS)
                    if eu >= 2:
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
                pl["toll_pending"] *= 2.0     # 下一回合付的过路费翻倍
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
                pl["stay"] = max(pl["stay"], 1)     # 卖身还钱，原地停留一回合
        elif idx == 3:
            pl["cash"] += 2000 if win else -2000
        elif idx == 4:
            if win:
                pl["cash"] += 1000
            else:
                pl["jail"] = 1
        elif idx == 5:
            # 巫祝祝福/诅咒：下回合你的过路费「收入」翻倍 / 减半
            pl["rent_pending"] *= 2.0 if win else 0.5
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
        elif idx == 11:
            if win:
                pl["cash"] += 800
            else:
                pl["mute_pending"] = True    # 禁言：下回合不能买/升级/拍卖/用道具
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
        elif idx == 15:
            self.limit_parity = True          # 单双号限行：下回合单数原地停留
        elif idx == 16:
            mine = [c for c in range(N_CELLS) if self.owner[c] == pl["idx"]]
            if mine:
                c = max(mine, key=lambda x: self.tiles[x]["price"])
                if win:
                    # 两倍总价收购，可以拒卖 → AI 只肯卖掉非目标组的房子
                    if self.tiles[c].get("colorId") != pl["target"]:
                        pl["cash"] += self.invested(c) * 2
                        self.owner[c] = None
                        self.level[c] = 0
                else:
                    pl["cash"] += self.invested(c)     # 正常总价，强制卖
                    self.owner[c] = None
                    self.level[c] = 0
        elif idx == 17:
            x = self.roll()
            d = 1 if self.roll() % 2 == 1 else -1
            pl["pos"] = (pl["pos"] + x * d) % N_CELLS
            self.resolve(pl)
        elif idx == 18:
            tgt = self.ahead(pl)              # 与前进方向最近的玩家对决
            if tgt is not None:
                v = max(0, int(tgt["cash"] * 0.2 // 10 * 10))
                if v > 0:
                    if win:
                        self.pay(tgt, v, pl)
                    else:
                        self.pay(pl, v, tgt)
        elif idx == 19:
            pl["cash"] += (self.roll() * 200 - 1600) if win else -800
        elif idx == 20:
            # 摇两次：单=善 / 双=恶，点数 X = 前方第 X 个玩家，其所在格房子 ±1 级
            good = self.roll() % 2 == 1
            tgt = self.ahead(pl, self.roll())
            if tgt is not None and self.owner[tgt["pos"]] is not None:
                c = tgt["pos"]
                self.level[c] = (min(5, self.level[c] + 1) if good
                                 else max(0, self.level[c] - 1))
        if pl["cash"] < 0:
            self.pay(pl, -pl["cash"])

    # ---------- 道具 ----------
    def my_cells(self, pl):
        return [c for c in range(N_CELLS) if self.owner[c] == pl["idx"]]

    def target_cells(self, pl):
        return [c for c in self.my_cells(pl)
                if self.tiles[c].get("colorId") == pl["target"]]

    def aim_target(self, pl, steps=None):
        """沿前进方向，找一步能落到「自己名下地产」的最小步数。"""
        rng_steps = range(1, DICE_FACES + 1) if steps is None else steps
        mine = set(self.my_cells(pl))
        for s in sorted(rng_steps):
            if (pl["pos"] + s * pl["direction"]) % N_CELLS in mine:
                return s
        return None

    def upgradable(self, pl):
        cands = [c for c in self.target_cells(pl) if self.level[c] < 5]
        return min(cands, key=lambda c: self.tiles[c]["price"]) if cands else None

    def enemy_house(self, pl, lvl):
        cands = [c for c in range(N_CELLS)
                 if self.owner[c] is not None and self.owner[c] != pl["idx"]
                 and self.level[c] >= lvl]
        return max(cands, key=lambda c: self.tiles[c]["price"]) if cands else None

    def maxed_group(self, pl):
        tc = self.target_cells(pl)
        return bool(tc) and all(self.level[c] == 5 for c in tc)

    def strongest_rival(self, pl):
        return self.richest(exclude=pl)

    def prop_value(self, pl, name):
        """这件道具对这名玩家当前局势的价值（>0 才会买）。"""
        if name == "遥控骰子":
            return 3.0 if self.aim_target(pl) is not None else 0.0
        if name == "汽车":
            return 2.0 if self.aim_target(pl, range(1, 2 * DICE_FACES + 1)) else 0.0
        if name == "工程机器人":
            return 2.5 if self.upgradable(pl) is not None else 0.0
        if name == "导弹":
            return 2.5 if self.enemy_house(pl, 4) is not None else 0.0
        if name == "红卡":
            return 1.5 if self.maxed_group(pl) else 0.0
        if name == "绿卡":
            return 1.0
        if name in ("免责卡", "嫁祸卡"):
            return 0.6
        if name in ("冷冻枪", "转向卡", "乌龟帽"):
            return 0.8
        if name == "拍卖卡":
            return 1.2 if self.enemy_house(pl, 3) is not None else 0.0
        if name == "抢夺卡":
            return 0.4 if any(p["props"] for p in self.players
                              if p is not pl and p["alive"]) else 0.0
        return 0.0                      # 路障：本版未建模效果，AI 不买

    def shop_visit(self, pl):
        """踩到商店格：随机刷 3 件，按需购买。"""
        if pl["mute"]:
            return
        self.shop_visits += 1
        stock = sorted(self.rng.sample(list(PROPS), 3),
                       key=lambda n: -self.prop_value(pl, n))
        for name in stock:
            if len(pl["props"]) >= MAX_PROPS:
                break
            if self.prop_value(pl, name) <= 0:
                continue
            if pl["cash"] - PROPS[name] >= PROP_RESERVE:
                pl["cash"] -= PROPS[name]
                pl["props"].append(name)
                self.props_bought += 1

    def avatar_escape(self, pl):
        """用免责卡 / 嫁祸卡抵消一次坐牢（返回 True = 逃掉了）。"""
        if "免责卡" in pl["props"]:
            pl["props"].remove("免责卡")
            return True
        if "嫁祸卡" in pl["props"]:
            pl["props"].remove("嫁祸卡")
            v = self.ahead(pl)
            if v is not None:
                v["jail"] = max(v["jail"], 1)
                v["pos"] = JAIL_CELL
            return True
        return False

    def use_props(self, pl):
        """回合开始前使用道具。"""
        if not self.props_enabled or pl["mute"] or not pl["props"]:
            return
        # 遥控骰子：直接把自己送到自家地产上
        if "遥控骰子" in pl["props"]:
            s = self.aim_target(pl)
            if s is not None:
                pl["props"].remove("遥控骰子")
                pl["pos"] = (pl["pos"] + s * pl["direction"]) % N_CELLS
                self.resolve(pl)
                return
        if "汽车" in pl["props"] and self.aim_target(pl, range(1, 2 * DICE_FACES + 1)):
            pl["props"].remove("汽车")
            pl["double_move"] = True                 # 下次移动双倍格数
        if "工程机器人" in pl["props"]:
            c = self.upgradable(pl)
            if c is not None:
                pl["props"].remove("工程机器人")
                self.level[c] += 1                   # 免费升一级
        if "导弹" in pl["props"]:
            c = self.enemy_house(pl, 3)
            if c is not None:
                pl["props"].remove("导弹")
                self.level[c] -= 1                   # 降级对手的房子
        if "拍卖卡" in pl["props"]:
            c = self.enemy_house(pl, 1)
            if c is not None:
                pl["props"].remove("拍卖卡")
                o = self.players[self.owner[c]]
                o["cash"] += self.invested(c) * AUCTION_RECOVERY
                self.owner[c] = None
                self.level[c] = 0
        if "抢夺卡" in pl["props"]:
            v = self.strongest_rival(pl)
            if v is not None and v["props"]:
                pl["props"].remove("抢夺卡")
                pl["props"].append(v["props"].pop(self.rng.randrange(len(v["props"]))))
        for name in ("乌龟帽", "冷冻枪", "转向卡"):
            if name in pl["props"]:
                v = self.strongest_rival(pl)
                if v is not None:
                    pl["props"].remove(name)
                    if name == "乌龟帽":
                        v["slow"] = 3                # 3 回合只能走 1 格
                    elif name == "冷冻枪":
                        v["stay"] = max(v["stay"], 1)   # 原地停 1 回合
                    else:
                        v["direction"] *= -1            # 掉头

    # ---------- 一回合 ----------
    def turn(self, pl):
        if pl["jail"] > 0:
            pl["jail"] -= 1
            return
        if pl["stay"] > 0:                       # 原地停留（机会 4/7、命运 2）
            pl["stay"] -= 1
            return
        # 激活上一回合挂起的「下一回合」状态；本回合结束后统一清掉
        pl["rent_mult"], pl["rent_pending"] = pl["rent_pending"], 1.0
        pl["toll_mult"], pl["toll_pending"] = pl["toll_pending"], 1.0
        pl["mute"], pl["mute_pending"] = pl["mute_pending"], False
        parity = self.limit_parity               # 命运 15：本回合单数原地停留
        self.limit_parity = False
        try:
            self.use_props(pl)
            if not pl["alive"]:
                return
            streak = 0
            while True:
                raw = self.roll()
                is16 = raw == DICE_FACES
                if parity and raw % 2 == 1:      # 单数：原地不动
                    return
                r = raw
                if pl["slow"] > 0:               # 乌龟帽：只能走 1 格
                    r = 1
                    pl["slow"] -= 1
                if pl["double_move"]:            # 汽车：这次移动双倍格数
                    r *= 2
                    pl["double_move"] = False
                streak = streak + 1 if is16 else 0
                self.move(pl, r)
                if not pl["alive"]:
                    return
                if pl["jail"] > 0:               # 被卡牌送进监狱
                    if not self.avatar_escape(pl):
                        pl["pos"] = JAIL_CELL
                        return
                    pl["jail"] = 0
                if self.arrive_jail and pl["pos"] == JAIL_CELL:
                    if not self.avatar_escape(pl):  # 走到北极也坐牢（A/B 口径）
                        pl["jail"] = 1
                        return
                if is16 and streak >= 2:         # 连续两次 16
                    if not self.avatar_escape(pl):
                        pl["jail"] = 1
                        pl["pos"] = JAIL_CELL
                        return
                if is16:
                    continue
                if pl["extra"] > 0:
                    pl["extra"] -= 1
                    continue
                return
        finally:
            pl["rent_mult"] = 1.0
            pl["toll_mult"] = 1.0
            pl["mute"] = False


def run_game(rng, data, targets, max_rounds=600, props=None, arrive_jail=None):
    g = Game(rng, data, targets)
    if props is not None:
        g.props_enabled = props
    if arrive_jail is not None:
        g.arrive_jail = arrive_jail
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


def ab_main():
    """A/B：道具系统 × 北极坐牢口径，2×2 四格对照。"""
    data = load_map()
    groups = {g["id"]: g for g in data["colorGroups"]}
    tiles = {t["id"]: t for t in data["tiles"]}
    score = []
    for g in data["colorGroups"]:
        ids = [t["id"] for t in data["tiles"] if t.get("colorId") == g["id"]]
        score.append((len(ids) * sum(tiles[i]["price"] for i in ids), g["id"]))
    score.sort(reverse=True)
    order = [gid for _, gid in score][:8]
    trials = int(os.environ.get("TRIALS", "250"))
    print("=" * 90)
    print(f"规则 2 · 完整对局 A/B：道具系统 × 北极坐牢口径（8 人混战 × {trials} 局/格）")
    print("=" * 90)
    print(f"\n  {'配置':<24}{'平均回合':>9}{'打完比例':>9}{'黄绿夺冠':>9}"
          f"{'道具购买/局':>12}{'平均破产':>9}")
    print("  " + "-" * 78)
    results = {}
    for props in (False, True):
        for aj in (False, True):
            rng = random.Random(424242)
            wins, rounds, ended, bought, dead = Counter(), [], [], [], []
            for _ in range(trials):
                targets = order[:]
                rng.shuffle(targets)
                w, g, r, ok = run_game(rng, data, targets, props=props,
                                       arrive_jail=aj)
                wins[w["target"]] += 1
                rounds.append(r)
                ended.append(ok)
                bought.append(g.props_bought)
                dead.append(sum(1 for p in g.players if not p["alive"]))
            results[(props, aj)] = wins
            tag = ("道具" if props else "无道具") + " · " + ("走到北极坐牢"
                                                        if aj else "只有被送才坐牢")
            print(f"  {tag:<24}{sum(rounds) / len(rounds):>9.0f}"
                  f"{sum(ended) / len(ended) * 100:>8.1f}%"
                  f"{wins[order[0]] / trials * 100:>8.1f}%"
                  f"{sum(bought) / len(bought):>12.1f}"
                  f"{sum(dead) / len(dead):>9.2f}")
    print("\n  逐组夺冠率：无道具 → 有道具（同一套北极口径）")
    for aj in (False, True):
        a, b = results[(False, aj)], results[(True, aj)]
        print(f"    ▸ {'走到北极坐牢' if aj else '只有被送才坐牢'}：")
        for gid in order:
            g = groups[gid]
            print(f"      {g['icon']}{g['name']:<10}"
                  f"{a[gid] / trials * 100:>6.1f}% → {b[gid] / trials * 100:>6.1f}%"
                  f"   ({b[gid] / trials * 100 - a[gid] / trials * 100:+.1f})")
    print(f"\n  黄绿 = 排序第 1 的组（6 格 2 段，满级连锁 $42,000）；"
          f"平均破产满分 8（= 8 表示全部打到只剩一人）")


def main():
    if os.environ.get("AB"):
        ab_main()
        return
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

