#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则 v3 · 完整对局模拟（8 人混战，打到只剩一个或到回合上限）。

跟 sim/landing.py 的落点模拟不同，这里跑的是「一局完整游戏」：买卖地产、升级房子、
连锁收租、付不出钱就拍卖、破产退出。用来回答「如果一组归你、另一组归他，谁更可能活到最后」。

【口径 = source/remix/manual-v3.md（站点默认版本）】
  · 骰子 / 起点 / 赤道酬金：1 枚十六面骰，摇到 16 再摇一次，连续两次 16 坐牢 1 回合；
    统一赤道 #0、同方向顺时针出发（v3 备选玩法「四角随机起点 + 单双定方向」不用）。
  · 地图格子类型不硬编码，全部读 JSON 的 variants.v2.replace：
    北极 #32 → 监狱，印度洋 #24 / 大西洋 #59 → 道具商店（太平洋 #10 仍是普通海洋格）。
  · 过路费 / 升级费 / 连锁按 v3；升级**只能升脚下这一格**（v3「必须走到自己的地产才能购买/升级」）。
  · 抽卡 = **16 张牌池 + 掷骰点选**：开局从 20 张里随机取 16 张成本局牌池，
    踩到格子摇 d16、按点数取对应那张，执行完放回池底（机会 / 命运各自一副）。
  · 监狱 = 北极：跳过回合、不能收租、不能用道具；刑满出狱缴**保释金 1000 × 关押回合数**。
  · 破产清算 = 名下房产**逐一强制拍卖**（起拍价 = 已投入总额 50% 向下取整十，流拍归银行），
    所得 25% 上交银行、75% 归自己，连同剩余现金一起交给债主；缺口由债主自担。
  · 红卡 / 绿卡单次上限 8000；主动道具一回合最多用 1 件；工程机器人盖不出红房（≤4 级）。
  · 胜负：最后未破产者胜；到回合上限（默认 600，`MAX_ROUNDS=150` 可试 v3 的加速口径）
    按**净值 = 现金 + 名下房产已投入成本**排名。
  · **卡牌已全量建模**：v7 的 20 张机会 + 20 张命运；条件牌赢面从 `cards.md` 的「命中率」列读，
    不再手抄进脚本。
  · **道具已建模 14 种**：AI 只在「有确定性收益」时买与用（遥控骰子推进自家地、
    工程机器人免费升级、导弹降级对手满级房…）。
  · **未建模**：路障（无效果）、拍卖场上的玩家竞价（按底价成交）、玩家之间的讨价还价与交易。
    因此绝对破产圈数偏乐观，但**组与组之间的相对排名可信**。
  · 8 名玩家各自锁定一个目标色组（政策相同），全部从赤道出发。

【A/B 开关】（环境变量；v3 里有几条是【建议】条款，用开关量出它的影响）
  BAIL=0         关掉保释金（回到 v2「坐牢免费」口径，用来验证这条修复到底改变了什么）
  POOL16=0       关掉 16 张牌池，回到 20 张等概率随机抽
  MAX_ROUNDS=150 回合上限（v3 的 150 回合加速胜利口径；默认 600）
  TRIALS=250     每个配置跑多少局

用法：
  python3 sim/game.py                     # 单配置：8 人各锁一组
  BAIL=0 python3 sim/game.py              # A/B：保释金开 / 关
  AB=1 python3 sim/game.py                # 2×2 对照：道具 × 北极坐牢
  COHORT=1 python3 sim/game.py            # A/B：集中同色 vs 到处撒
  LEDGER=1 TRIALS=600 python3 sim/game.py # 单回合净值账本
  AUDIT=1 TRIALS=600 python3 sim/game.py  # 逐张卡牌实战净值插桩
"""

import json
import os
import random
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_JSON = os.path.join(ROOT, "source", "remix", "map.json")

N_CELLS = 64
GO_CELL = 0             # 赤道：统一出生点
DICE_FACES = 16
GO_BONUS = 2000
START_CASH = 15000

# 命运牌判定率（rate = 赢面）：从 source/remix/cards.md 的「命中率」列读，不再手抄
# （单一真源）。解析失败才退回写死的兜底，并打印警告。
def _parse_rate(s):
    s = (s or "").strip().replace("%", "")
    try:
        x = float(s)
    except ValueError:
        return None
    return x / 100.0 if x > 1 else x

def load_fate_rates():
    """读 cards.md 默认版本的命运牌，返回 {idx(1-20): 赢面浮点}。"""
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import lib.cards as cards_lib
        text = open(cards_lib.paths.CARDS_MD_PATH, encoding="utf-8").read()
        rows, _labels, errs = cards_lib.parse_cards_md(text)
        if errs:
            raise ValueError("cards.md 结构错误: " + errs[0])
        ver = cards_lib.DEFAULT_VERSION
        rates, order = {}, 0
        for r in rows:
            if r.get("deck") != "fate" or r.get("version") != ver:
                continue
            order += 1
            rate = _parse_rate(r.get("rate"))
            if rate is not None:
                rates[order] = rate
        if len(rates) != 20:
            raise ValueError("命运牌不足 20 张: %d" % len(rates))
        return rates
    except Exception as e:
        sys.stderr.write("[warn] 命运牌判定率回退写死值：%s\n" % e)
        return {1:0.50,2:0.50,3:0.50,4:0.50,5:0.50,6:0.50,7:0.375,
                8:0.1875,9:0.9375,10:0.3125,11:0.50,12:0.50,13:0.25,
                14:0.50,15:0.50,16:0.50,17:0.50,18:0.50,19:0.50,20:0.50}

FATE = load_fate_rates()


def load_map():
    with open(MAP_JSON, encoding="utf-8") as f:
        return json.load(f)


def v2_board(data):
    """按 JSON 的 variants.v2.replace 覆盖格子，返回 (tiles, 监狱格, 商店格集合)。

    ⚠️ 监狱 / 商店的位置**只由 JSON 决定**，脚本里不写死：
       北极 #32 → 监狱；印度洋 #24 / 大西洋 #59 → 道具商店（太平洋 #10 仍是海洋）。
    """
    var = (data.get("variants") or {}).get("v2") or {}
    patch = {int(k): v for k, v in (var.get("replace") or {}).items()}
    tiles = []
    for t in data["tiles"]:
        t = dict(t)
        t.update(patch.get(t["id"], {}))
        tiles.append(t)
    jail = next(t["id"] for t in tiles if t["type"] == "jail")
    shops = {t["id"] for t in tiles if t["type"] == "shop"}
    return {t["id"]: t for t in tiles}, jail, shops


BUY_BUFFER = 1000        # 买地后至少留这么多现金
UPGRADE_BUFFER = 2500    # 升级后至少留这么多现金
OPPORTUNISTIC_CASH = 5000   # 手头超过这个数才会顺手买非目标组的地
OPPORTUNISTIC_MAX_PRICE = 1200
AUCTION_RECOVERY = 0.375    # 拍卖实际回收比例（50% 底价 × 75% 归自己）

# 机会 12「欧洲区域玩家每人付你 1000」的判定集合（俄罗斯/波兰/德国/奥地利/瑞士/法国/
# 比利时/荷兰/英国/芬兰/瑞典/丹麦/希腊/意大利/西班牙/葡萄牙）
EUROPE_CELLS = {21, 22, 23, 25, 26, 27, 28, 30, 31, 33, 34, 35, 36, 37, 39, 40}

# ==================== 道具系统 ====================
# ⚠️ 商店格口径：直接读 JSON 的 variants.v2 —— 印度洋 #24 / 大西洋 #59 是道具商店。
#    （open 时由 v2_board() 写入 Game.shop_cells；太平洋 #10 仍是普通海洋格。）
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
ARRIVE_JAIL_CELL_JAILS = True    # 走到监狱格（北极 #32）也强制坐牢；False = 只有被送才坐牢

# 规则写明「坐牢期间不能收租」，但早期版本漏实现。True = 按规则（地主坐牢 = 全场免租）
JAIL_NO_RENT = os.environ.get("JAIL_NO_RENT", "1") == "1"
# 道具每种几张（规则：每种 2 张）。None = 不限量（旧口径，做对照用）
PROP_STOCK_PER_KIND = None if os.environ.get("PROP_UNLIMITED") else 2
# 卡牌实战插桩：AUDIT=1 时逐张记录触发次数与净值变化
AUDIT = os.environ.get("AUDIT") == "1"
# 单回合净值账本：LEDGER=1 时逐回合记录净值变化（验证「坐牢代价」等口径）
LEDGER = os.environ.get("LEDGER") == "1"

# ---- v3 的 A/B 开关（环境变量；见文件头说明）----
BAIL_ON = os.environ.get("BAIL", "1") != "0"          # 保释金 = 1000 × 关押回合数
POOL16_ON = os.environ.get("POOL16", "1") != "0"      # 16 张牌池 + 掷骰点选
MAX_ROUNDS = int(os.environ.get("MAX_ROUNDS", "600"))  # 回合上限（v3 加速口径 150）
RED_GREEN_CAP = 8000        # 红卡 / 绿卡单次效果上限
ACTIVE_PROP_PER_TURN = 1    # 主动道具每回合最多使用件数
BAIL_PER_ROUND = 1000       # 保释金每回合单价


class Game:
    def __init__(self, rng, data, targets):
        self.rng = rng
        self.data = data
        self.tiles, self.jail, self.shop_cells = v2_board(data)
        self.owner = [None] * N_CELLS      # 玩家编号
        self.level = [0] * N_CELLS         # 0..5
        self.limit_parity = False          # 命运 15：下一回合单数原地停留
        self.props_enabled = PROPS_ENABLED
        self.arrive_jail = ARRIVE_JAIL_CELL_JAILS
        self.shop_visits = 0
        self.props_bought = 0
        self.shop_stock = {}               # 本店刷新出来的道具（全局共用一副牌堆）
        self.prop_stock = (dict((n, PROP_STOCK_PER_KIND) for n in PROPS)
                           if PROP_STOCK_PER_KIND else None)   # 每种剩余张数
        self.audit = {}                    # AUDIT 插桩：(kind, idx) -> 统计
        self.pending_audit = []            # 待结算（等本回合走完再记账）
        self.jail_cost = 0.0               # 坐牢净值成本累计
        self.jail_events = 0
        self.jail_lead_cost = self.jail_lead_n = 0
        self.jail_big_cost = self.jail_big_n = 0
        self.ledger = []                   # LEDGER 插桩：(回合, 玩家, 模式, 净值Δ)
        self.flow = Counter()              # LEDGER 资金流分解（赤道/过路费/坐牢拒收）
        self.round_no = 0                  # 当前进行到第几回合（破产计时用）
        self.first_death_round = None
        self.player_turns = 0              # 累计「人·回合」数（= 真人掷骰次数）
        self.prop_buy_counts = Counter()   # 每种道具的购买次数
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
                bail_due=0,                        # 出狱待缴保释金（v3）
            ))
        # v3 抽卡牌池：开局从 20 张各取 16 张成本局牌池（机会/命运各自一副）
        self.deck_chance = self._build_deck(rng)
        self.deck_destiny = self._build_deck(rng)

    def _build_deck(self, rng):
        """从 1-20 随机取 16 张成本局牌池（4 张不亮出）。"""
        base = list(range(1, 21))
        rng.shuffle(base)
        return base[:16]

    def _enter_jail(self, pl, rounds):
        """送进监狱（北极），并记录保释金（v3：1000 × 关押回合数，出狱缴）。"""
        if pl["jail"] == 0 and BAIL_ON:
            pl["bail_due"] = BAIL_PER_ROUND * rounds
        pl["jail"] = max(pl["jail"], rounds)

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
            pl["props"].remove("绿卡")      # 绿卡：抵消一次付款（单次上限 8000）
            if amount <= RED_GREEN_CAP:
                return True
            amount -= RED_GREEN_CAP         # 超出部分照付
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
        if self.first_death_round is None:
            self.first_death_round = self.round_no
        mine = [c for c in range(N_CELLS) if self.owner[c] == pl["idx"]]
        cash_to_creditor = pl["cash"]
        pl["cash"] = 0
        for c in mine:
            invested = self.invested(c)
            start = int(invested * 0.5 // 10 * 10)   # 起拍价 = 已投入 50% 取整十
            # 拍卖：找买得起的存活玩家（50% 折扣必捡漏，只要有钱）；债主本人优先 reclaim
            buyers = [p for p in self.players
                      if p["alive"] and p is not pl and p["cash"] >= start]
            buyer = None
            if buyers:
                if creditor is not None and creditor["alive"] and creditor["cash"] >= start:
                    buyer = creditor
                else:
                    buyer = max(buyers, key=lambda p: p["cash"])
            if buyer is not None:
                buyer["cash"] -= start
                self.owner[c] = buyer["idx"]
                self.level[c] = 0
                if creditor is not None:
                    creditor["cash"] += start * 0.75   # 75% 归债主，25% 归银行
            else:
                self.owner[c] = None     # 流拍归银行
                self.level[c] = 0
        if creditor is not None:
            creditor["cash"] += cash_to_creditor

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
            self.flow["go"] += GO_BONUS
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
        elif self.props_enabled and t["type"] == "shop":
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
        if JAIL_NO_RENT and other["jail"] > 0:
            self.flow["rent_denied_n"] += 1
            self.flow["rent_denied"] += self.chain_rent(cell, owner)
            return                         # 规则：坐牢期间不能收租
        # 机会 18（付方翻倍）× 命运 5（收方翻倍/减半）
        rent = self.chain_rent(cell, owner) * pl["toll_mult"] * other["rent_mult"]
        if rent >= RED_CARD_MIN and "红卡" in other["props"]:
            other["props"].remove("红卡")   # 红卡：让这一次收款翻倍（单次上限 8000）
            rent += min(rent, RED_GREEN_CAP)
        self.flow["rent"] += rent
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

    # ---------- 卡牌实战插桩（AUDIT=1 时启用）----------
    def snapshot(self):
        """净值快照：每人的现金 + 名下房产的「已投入成本」。"""
        return dict(
            cash=[p["cash"] for p in self.players],
            alive=[p["alive"] for p in self.players],
            est=[(self.owner[c], self.level[c]) for c in range(N_CELLS)],
        )

    def _worth(self, pairs, i):
        tot = 0.0
        for c, (o, lv) in enumerate(pairs):
            if o != i:
                continue
            p = self.tiles[c]["price"]
            cost = p
            for s in range(1, lv + 1):
                cost += p * (1.0 if s == 5 else 0.5)
            tot += cost
        return tot

    def networth(self, i):
        """LEDGER：一人的当前净值（现金 + 名下房产已投入成本）。"""
        pairs = [(self.owner[c], self.level[c]) for c in range(N_CELLS)]
        return self.players[i]["cash"] + self._worth(pairs, i)

    def audit_card(self, kind, idx, snap, who):
        """记录一张牌触发前后的净值变化（抽卡者 vs 其余人）。"""
        d = self.audit.setdefault((kind, idx),
                                  dict(n=0, self=0.0, oth=0.0, lead_n=0,
                                       lead_self=0.0, mx=0.0, omx=0.0,
                                       deaths=0))
        pairs_now = [(self.owner[c], self.level[c]) for c in range(N_CELLS)]
        now = [pl["cash"] + self._worth(pairs_now, i)
               for i, pl in enumerate(self.players)]
        was = [snap["cash"][i] + self._worth(snap["est"], i)
               for i in range(len(self.players))]
        lead = max(range(len(self.players)), key=lambda i: was[i])
        d["n"] += 1
        d["self"] += now[who] - was[who]
        d["oth"] += sum(now[i] - was[i] for i in range(len(self.players)) if i != who)
        if who == lead:
            d["lead_n"] += 1
            d["lead_self"] += now[who] - was[who]
        d["mx"] = max(d["mx"], abs(now[who] - was[who]))
        d["omx"] = max(d["omx"], abs(sum(now[i] - was[i]
                                        for i in range(len(self.players))
                                        if i != who)))
        d["deaths"] += sum(1 for i, p in enumerate(self.players)
                           if snap["alive"][i] and not p["alive"])

    def resolve_card(self, pl, kind):
        pool = self.deck_chance if kind == "chance" else self.deck_destiny
        if POOL16_ON and pool:
            # 16 张牌池 + 掷骰点选：摇 d16 取对应那张，执行完放回池底
            r = self.rng.randint(1, len(pool))
            idx = pool[r - 1]
            pool.append(pool.pop(r - 1))
        else:
            idx = self.rng.randint(1, 20)
        if AUDIT:
            # 结算点延到「该玩家本回合结束」——这样额外移动（机会 7/14、命运 17）
            # 与引发的连锁破产也能计入该卡的影响
            self.pending_audit.append((kind, idx, self.snapshot(), pl["idx"]))
        self.card_effect(pl, kind, idx)

    def flush_audit(self):
        for kind, idx, snap, who in self.pending_audit:
            self.audit_card(kind, idx, snap, who)
        self.pending_audit = []

    def card_effect(self, pl, kind, idx):
        rng = self.rng
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
                    self._enter_jail(pl, 3)
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
                self._enter_jail(pl, 3)
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
                self._enter_jail(pl, 1)
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
                self._enter_jail(pl, 1)
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
            # 卡面「前进/后退 X 格」= 正常移动，经过赤道照给酬金
            x = self.roll()
            d = 1 if self.roll() % 2 == 1 else -1
            self.move(pl, x * d)
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
            # 卡面：摇判定骰 X，X≥9 中奖、奖金 = X×200−1600（+200~+1600）；否则 -800
            x = self.roll()
            pl["cash"] += (x * 200 - 1600) if x >= 9 else -800
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
        pool = list(PROPS)
        if self.prop_stock is not None:          # 限量：只从有货的里刷
            pool = [n for n in pool if self.prop_stock[n] > 0]
            pool = pool[:3] if len(pool) <= 3 else self.rng.sample(pool, 3)
        else:
            pool = self.rng.sample(pool, 3)
        stock = sorted(pool, key=lambda n: -self.prop_value(pl, n))
        for name in stock:
            if len(pl["props"]) >= MAX_PROPS:
                break
            if self.prop_value(pl, name) <= 0:
                continue
            if pl["cash"] - PROPS[name] >= PROP_RESERVE:
                pl["cash"] -= PROPS[name]
                pl["props"].append(name)
                self.props_bought += 1
                self.prop_buy_counts[name] += 1
                if self.prop_stock is not None:
                    self.prop_stock[name] -= 1

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
                v["pos"] = self.jail
            return True
        return False

    def use_props(self, pl):
        """回合开始前使用道具；v3：主动道具一回合最多用 ACTIVE_PROP_PER_TURN 件。"""
        if not self.props_enabled or pl["mute"] or not pl["props"]:
            return
        used = 0
        def can():
            return used < ACTIVE_PROP_PER_TURN
        # 遥控骰子：直接把自己送到自家地产上
        if can() and "遥控骰子" in pl["props"]:
            s = self.aim_target(pl)
            if s is not None:
                pl["props"].remove("遥控骰子")
                used += 1
                pl["pos"] = (pl["pos"] + s * pl["direction"]) % N_CELLS
                self.resolve(pl)
                if not pl["alive"]:
                    return
        if can() and "汽车" in pl["props"] and self.aim_target(pl, range(1, 2 * DICE_FACES + 1)):
            pl["props"].remove("汽车")
            used += 1
            pl["double_move"] = True                 # 下次移动双倍格数
        if can() and "工程机器人" in pl["props"]:
            c = self.upgradable(pl)
            if c is not None:
                pl["props"].remove("工程机器人")
                used += 1
                self.level[c] += 1                   # 免费升一级
        if can() and "导弹" in pl["props"]:
            c = self.enemy_house(pl, 3)
            if c is not None:
                pl["props"].remove("导弹")
                used += 1
                self.level[c] -= 1                   # 降级对手的房子
        if can() and "拍卖卡" in pl["props"]:
            c = self.enemy_house(pl, 1)
            if c is not None:
                pl["props"].remove("拍卖卡")
                used += 1
                o = self.players[self.owner[c]]
                o["cash"] += self.invested(c) * AUCTION_RECOVERY
                self.owner[c] = None
                self.level[c] = 0
        if can() and "抢夺卡" in pl["props"]:
            v = self.strongest_rival(pl)
            if v is not None and v["props"]:
                pl["props"].remove("抢夺卡")
                used += 1
                pl["props"].append(v["props"].pop(self.rng.randrange(len(v["props"]))))
        for name in ("乌龟帽", "冷冻枪", "转向卡"):
            if can() and name in pl["props"]:
                v = self.strongest_rival(pl)
                if v is not None:
                    pl["props"].remove(name)
                    used += 1
                    if name == "乌龟帽":
                        v["slow"] = 3                # 3 回合只能走 1 格
                    elif name == "冷冻枪":
                        v["stay"] = max(v["stay"], 1)   # 原地停 1 回合
                    else:
                        v["direction"] *= -1            # 掉头

    def audit_jail(self, who, snap):
        """坐牢事件的净值成本（AUDIT 用）。"""
        pairs_now = [(self.owner[c], self.level[c]) for c in range(N_CELLS)]
        now = [pl["cash"] + self._worth(pairs_now, i)
               for i, pl in enumerate(self.players)]
        was = [snap["cash"][i] + self._worth(snap["est"], i)
               for i in range(len(self.players))]
        d = now[who] - was[who]
        self.jail_cost += d
        lead = max(range(len(self.players)), key=lambda i: was[i])
        if who == lead:
            self.jail_lead_cost += d
            self.jail_lead_n += 1
        mine = sum(1 for c in range(N_CELLS) if self.owner[c] == who)
        if mine >= 3:                       # 大地主：名下 ≥3 块地
            self.jail_big_cost += d
            self.jail_big_n += 1

    # ---------- 一回合 ----------
    def turn(self, pl):
        if LEDGER:
            v0 = self.networth(pl["idx"])
        if pl["jail"] > 0:
            if pl.get("_ja") is None:                # 入狱窗口净值（常态收集，AUDIT 不必开）
                pl["_ja"] = self.snapshot()
            pl["jail"] -= 1
            if pl["jail"] == 0:
                if BAIL_ON and pl.get("bail_due"):
                    bail = pl.pop("bail_due")
                    self.pay(pl, bail)               # 保释金交给银行（付不出→破产）
                if pl["alive"] and pl.get("_ja") is not None:
                    self.audit_jail(pl["idx"], pl.pop("_ja"))
                    self.jail_events += 1
            if LEDGER:
                self.ledger.append((self.round_no, pl["idx"], "jail",
                                    self.networth(pl["idx"]) - v0))
            return
        if pl["stay"] > 0:                       # 原地停留（机会 4/7、命运 2）
            pl["stay"] -= 1
            if LEDGER:
                self.ledger.append((self.round_no, pl["idx"], "stay",
                                    self.networth(pl["idx"]) - v0))
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
                        pl["pos"] = self.jail
                        return
                    pl["jail"] = 0
                if self.arrive_jail and pl["pos"] == self.jail:
                    if not self.avatar_escape(pl):  # 走到监狱格也坐牢（默认口径，A/B 可关）
                        self._enter_jail(pl, 1)
                        return
                if is16 and streak >= 2:         # 连续两次 16
                    if not self.avatar_escape(pl):
                        self._enter_jail(pl, 1)
                        pl["pos"] = self.jail
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
            if LEDGER:
                self.ledger.append((self.round_no, pl["idx"], "normal",
                                    self.networth(pl["idx"]) - v0))
            if AUDIT:
                self.flush_audit()


def run_game(rng, data, targets, max_rounds=MAX_ROUNDS, props=None, arrive_jail=None):
    g = Game(rng, data, targets)
    if props is not None:
        g.props_enabled = props
    if arrive_jail is not None:
        g.arrive_jail = arrive_jail
    # 统一起点：所有人赤道 #0 出发、单向顺时针（v2 的四角随机起点与监狱冲突，不用）
    for pl in g.players:
        pl["pos"] = GO_CELL
        pl["direction"] = 1
    rounds_used = max_rounds
    for rd in range(max_rounds):
        g.round_no = rd
        alive = [p for p in g.players if p["alive"]]
        g.player_turns += len(alive)
        if len(alive) <= 1:
            rounds_used = rd
            break
        for pl in list(g.players):
            if pl["alive"]:
                g.turn(pl)
    alive = [p for p in g.players if p["alive"]]
    if len(alive) == 1:
        return alive[0], g, rounds_used, True
    # 到回合上限：按净值（现金 + 名下房产已投入成本）排名判胜
    return max(alive, key=lambda p: g.networth(p["idx"])), g, rounds_used, False


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
    print(f"规则 3（v3）· 完整对局 A/B：道具系统 × 监狱口径（8 人混战 × {trials} 局/格）")
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
            tag = ("道具" if props else "无道具") + " · " + ("走到监狱格坐牢"
                                                        if aj else "只有被送才坐牢")
            print(f"  {tag:<24}{sum(rounds) / len(rounds):>9.0f}"
                  f"{sum(ended) / len(ended) * 100:>8.1f}%"
                  f"{wins[order[0]] / trials * 100:>8.1f}%"
                  f"{sum(bought) / len(bought):>12.1f}"
                  f"{sum(dead) / len(dead):>9.2f}")
    print("\n  逐组夺冠率：无道具 → 有道具（同一套北极口径）")
    for aj in (False, True):
        a, b = results[(False, aj)], results[(True, aj)]
        print(f"    ▸ {'走到监狱格坐牢' if aj else '只有被送才坐牢'}：")
        for gid in order:
            g = groups[gid]
            print(f"      {g['icon']}{g['name']:<10}"
                  f"{a[gid] / trials * 100:>6.1f}% → {b[gid] / trials * 100:>6.1f}%"
                  f"   ({b[gid] / trials * 100 - a[gid] / trials * 100:+.1f})")
    print(f"\n  黄绿 = 排序第 1 的组（6 格 2 段，满级连锁 $42,000）；"
          f"平均破产满分 8（= 8 表示全部打到只剩一人）")


def ledger_main():
    """LEDGER=1：单回合净值账本——正常回合 vs 坐牢/停留回合的净值期望对照。

    回答「坐牢到底贵不贵」：两个独立口径互验——
      口径 A：坐牢窗口（入狱→出狱）的实际净值变化（与 balance-v7 同口径）
      口径 B：机会成本 = 同阶段正常回合的期望净值变化 × 坐牢时长 − 口径 A
    另附资金流分解（赤道注入 / 过路费 / 坐牢期间被拒收的租金）。
    """
    data = load_map()
    groups = {g["id"]: g for g in data["colorGroups"]}
    tiles = {t["id"]: t for t in data["tiles"]}
    score = []
    for gid, g in groups.items():
        ids = [t for t in data["tiles"] if t.get("colorId") == gid]
        total = sum(t["price"] for t in ids)
        score.append((len(ids) * total, gid))
    score.sort(reverse=True)
    order = [gid for _, gid in score][:8]
    trials = int(os.environ.get("TRIALS", "300"))
    rng = random.Random(20261014)
    led = []
    flow = Counter()
    jail_cost, jail_n = 0.0, 0
    for _ in range(trials):
        targets = order[:]
        rng.shuffle(targets)
        _w, g, r, ok = run_game(rng, data, targets)
        led.extend(g.ledger)
        flow.update(g.flow)
        jail_cost += g.jail_cost
        jail_n += g.jail_events

    T = float(trials)
    n = len(led)
    mean = lambda vals: sum(vals) / len(vals) if vals else float("nan")
    med = lambda vals: sorted(vals)[len(vals) // 2] if vals else float("nan")
    stages = [("前 52 回合(发育期)", lambda rd: rd < 52),
              ("52–150 回合(中期)", lambda rd: 52 <= rd <= 150),
              ("150 回合后(残局)", lambda rd: rd > 150)]

    print("=" * 78)
    print(f"单回合净值账本 · 8 人局 × {trials} 局 · 共 {n} 条回合记录"
          f"（净值 = 现金 + 名下房产已投入成本）")
    print("=" * 78)
    print(f"\n【口径 A · 坐牢窗口实际净值变化】{jail_n/T:.2f} 次/局 · "
          f"{jail_cost/jail_n:+.1f} 元/次（入狱→出狱整体，含他人回合）")
    for name, f in stages:
        ns = [d for rd, _p, m, d in led if m == "normal" and f(rd)]
        js = [d for rd, _p, m, d in led if m == "jail" and f(rd)]
        if not ns:
            continue
        print(f"\n【{name}】正常回合 {len(ns)} 条 · 坐牢跳过 {len(js)} 条")
        print(f"  正常回合 Δ净值：均值 {mean(ns):+8.0f} · 中位 {med(ns):+8.0f} 元/回合")
        if js:
            print(f"  坐牢回合 Δ净值：均值 {mean(js):+8.0f} · 中位 {med(js):+8.0f} 元/回合"
                  f"（跳过回合本身 ≈ 0 即验证账本无误）")
    ns_all = [d for _rd, _p, m, d in led if m == "normal"]
    js_all = [d for _rd, _p, m, d in led if m == "jail"]
    ss_all = [d for _rd, _p, m, d in led if m == "stay"]
    print(f"\n【合计】正常 {len(ns_all)} 条 · 坐牢 {len(js_all)} 条 · 停留 {len(ss_all)} 条")
    print(f"  全体正常回合：均值 {mean(ns_all):+.0f} · 中位 {med(ns_all):+.0f} 元/回合")
    print(f"  全体坐牢回合：均值 {mean(js_all):+.0f} 元/回合"
          f" · 停留回合：均值 {mean(ss_all):+.0f} 元/回合")
    if js_all:
        e_normal = mean(ns_all)
        opp = e_normal - mean(js_all)
        print(f"\n【口径 B · 机会成本】坐牢回合若正常行动，期望多变化 "
              f"{opp:+.0f} 元/回合（E[正常] − E[坐牢]）")
        print(f"  × 平均刑期 ≈ {len(js_all)/max(jail_n,1):.2f} 回合/次 → "
              f"每次坐牢的机会成本 ≈ {opp * len(js_all)/max(jail_n,1):+.0f} 元")
    print(f"\n【资金流分解】/局")
    print(f"  赤道酬金注入：{flow['go']/T:,.0f} 元")
    print(f"  过路费成交总额：{flow['rent']/T:,.0f} 元")
    if flow["rent_denied_n"]:
        print(f"  坐牢被拒收租金：{flow['rent_denied_n']/T:.2f} 次/局 · "
              f"共 {flow['rent_denied']/T:,.0f} 元/局 · "
              f"均 {flow['rent_denied']/flow['rent_denied_n']:,.0f} 元/次"
              f"（地主坐牢期间，别人踩他地不用付）")


def audit_main():
    """AUDIT=1：逐张卡牌的实战净值影响 + 道具购买分布 + 8 人局节奏。"""
    data = load_map()
    tiles = {t["id"]: t for t in data["tiles"]}
    score = []
    for g in data["colorGroups"]:
        ids = [t["id"] for t in data["tiles"] if t.get("colorId") == g["id"]]
        score.append((len(ids) * sum(tiles[i]["price"] for i in ids), g["id"]))
    score.sort(reverse=True)
    order = [gid for _, gid in score][:8]
    trials = int(os.environ.get("TRIALS", "300"))
    rng = random.Random(20261013)
    agg, pcount = {}, Counter()
    rounds, ended, dead, first_death, bought, visits = [], [], [], [], [], []
    jail_cost, jail_n = 0.0, 0
    pturns = []
    jl_cost, jl_n, jb_cost, jb_n = 0.0, 0, 0.0, 0
    for _ in range(trials):
        targets = order[:]
        rng.shuffle(targets)
        _w, g, r, ok = run_game(rng, data, targets)
        for k, v in g.audit.items():
            a = agg.setdefault(k, dict(n=0, self=0.0, oth=0.0, lead_n=0,
                                       lead_self=0.0, mx=0.0, omx=0.0,
                                       deaths=0))
            for f in ("n", "self", "oth", "lead_n", "lead_self", "deaths"):
                a[f] += v[f]
            a["mx"] = max(a["mx"], v["mx"])
            a["omx"] = max(a["omx"], v["omx"])
        pcount.update(g.prop_buy_counts)
        pturns.append(g.player_turns)
        jail_cost += g.jail_cost
        jail_n += g.jail_events
        jl_cost += g.jail_lead_cost
        jl_n += g.jail_lead_n
        jb_cost += g.jail_big_cost
        jb_n += g.jail_big_n
        rounds.append(r)
        ended.append(ok)
        dead.append(sum(1 for p in g.players if not p["alive"]))
        bought.append(g.props_bought)
        visits.append(g.shop_visits)
        if g.first_death_round is not None:
            first_death.append(g.first_death_round)

    T = float(trials)
    print("=" * 100)
    print(f"v7 卡牌实战插桩 · 8 人局 × {trials} 局"
          f"（统一赤道起点 / 走到监狱即坐牢 / 道具开 / 坐牢不能收租={JAIL_NO_RENT}）")
    print("=" * 100)
    print(f"\n【节奏】平均回合 {sum(rounds)/T:.0f} · 打完比例 "
          f"{sum(ended)/T*100:.1f}% · 平均破产 {sum(dead)/T:.2f}/8 · "
          f"道具购买 {sum(bought)/T:.1f} 件/局 · 商店访问 {sum(visits)/T:.1f} 次/局")
    rs = sorted(rounds)
    q = lambda p: rs[min(len(rs) - 1, int(len(rs) * p))]
    print(f"  回合数分位：p10 {q(.10)} · 中位 {q(.50)} · p90 {q(.90)} · "
          f"最长 {rs[-1]}")
    print(f"  总「人·回合」（真人掷骰次数）：平均 {sum(pturns)/T:.0f} 次/局"
          f"（每人平均 {(sum(pturns)/T)/8:.0f} 次）")
    if first_death:
        fs = sorted(first_death)
        print(f"  首次破产回合：中位 {fs[len(fs)//2]} · "
              f"p10 {fs[int(len(fs)*.10)]} · p90 {fs[min(len(fs)-1, int(len(fs)*.90))]}"
              f"（= 前 1/{max(1, round(sum(rounds)/T / max(fs[len(fs)//2], 1)))} 局是安全发育期）")
    if jail_n:
        print(f"【坐牢的真实成本】{jail_n/T:.2f} 次/局 · 每次平均净值变化 "
              f"{jail_cost/jail_n:+.0f} 元（负 = 亏，接近 0 = 无惩罚）")
        if jl_n:
            print(f"  ├ 领先者坐牢：{jl_cost/jl_n:+.0f} 元/次（{jl_n/T:.2f} 次/局）")
        if jb_n:
            print(f"  └ 大地主坐牢（名下≥3块地）：{jb_cost/jb_n:+.0f} 元/次"
                  f"（{jb_n/T:.2f} 次/局）")

    deck_name = {"chance": "机会", "destiny": "命运"}
    for kind in ("chance", "destiny"):
        print(f"\n【{deck_name[kind]}牌 · 实战净值影响】"
              f"（净值 = 现金 + 名下房产已投入成本）")
        print(f"  {'#':>3}{'触发/局':>8}{'抽卡者Δ':>9}{'其他人Δ':>9}"
              f"{'领先者Δ':>9}{'领先占比':>8}{'自身极值':>9}{'全场极值':>9}"
              f"{'触发破产':>9}")
        print("  " + "-" * 72)
        for idx in range(1, 21):
            a = agg.get((kind, idx))
            if not a or a["n"] == 0:
                continue
            lead = (a["lead_self"] / a["lead_n"]) if a["lead_n"] else float("nan")
            print(f"  {idx:>3}{a['n']/T:>8.2f}{a['self']/a['n']:>9.0f}"
                  f"{a['oth']/a['n']:>9.0f}{lead:>9.0f}"
                  f"{a['lead_n']/a['n']*100:>7.0f}%"
                  f"{a['mx']:>9.0f}{max(a['mx'], a['omx']):>9.0f}"
                  f"{a['deaths']/T:>9.2f}")

    print(f"\n【道具购买次数/局】（价格 / 总购买 {sum(pcount.values())/T:.1f} 件）")
    for name in sorted(PROPS, key=lambda n: -pcount[n]):
        print(f"  {name:<8} ${PROPS[name]:>5}  {pcount[name]/T:>6.2f} 次/局")


def main():
    if os.environ.get("AB"):
        ab_main()
        return
    if os.environ.get("COHORT"):
        cohort_main()
        return
    if os.environ.get("LEDGER"):
        ledger_main()
        return
    if os.environ.get("AUDIT"):
        audit_main()
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
    print(f"规则 3（v3）· 完整对局模拟：8 人混战 × {trials} 局（各自锁定一个目标色组）")
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
        for pl in g.players:          # 统一起点：赤道 #0、单向顺时针
            pl["pos"] = GO_CELL
            pl["direction"] = 1
        used = MAX_ROUNDS
        for rd in range(MAX_ROUNDS):
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
            w = max(alive, key=lambda p: g.networth(p["idx"]))
            if w.get("spread"):
                spread_wins += 1
            else:
                conc_wins += 1
    print("=" * 70)
    print(f"规则 3（v3）· A/B 对照：4 名「集中同色」vs 4 名「到处撒」× {trials} 局")
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

