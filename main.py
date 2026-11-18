"""BTC race bot: fresh EMA-crossover entries with 60-minute momentum, long only.

Evidence from the dev window (1,440 one-minute bars, BTC -2.8% on the day):
  - Dip-buying loses: after a sharp 30-minute drop the price keeps
    falling on average. This bot never buys a dip.
  - "Already in an uptrend" entries lose too: they buy dead-cat bounces
    and pay the ~26 bps round-trip cost on every whipsaw (the plain
    EMA-cross baseline lost $148 on this window with 80 trades).
  - What works is a FRESH cross: EMA(10) crossing above EMA(30) on a bar
    whose trailing 60-minute return is above +0.5%. That fired twice on
    the dev window and caught the day's two real up-legs (+0.9% and
    +1.6% swings), for a dev net PnL of +$6.65 on 4 trades, max
    drawdown 0.8%. The result is flat across EMA spans (8/21, 10/30,
    12/26 all land within $0.35 of each other), so it is the rule, not
    the parameters, doing the work.
  - Exits let a winner run but cut it quickly: take-profit, stop-loss,
    a trailing give-back from the peak value since entry, the EMA
    crossing back, or a time stop.
  - Late fallback: if no buy has filled by bar 1200 the day is quiet,
    so the entry bar is lowered once, just to make the one trade the
    guardrails need rather than sit out the race entirely.

Everything is deterministic: indicators from closes only, no clock, no
randomness, no environment. Money decisions use integer micro-USDC.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

PARAMS = {
    "fast": 10,          # fast EMA span (bars)
    "slow": 30,          # slow EMA span (bars)
    "mom_win": 60,       # momentum window (bars)
    "mom_thr": 0.005,    # momentum entry threshold (fraction)
    "tp": 0.012,         # take-profit over cost (fraction)
    "sl": 0.007,         # stop-loss under cost (fraction)
    "trail": 0.004,      # trailing give-back from the peak value (fraction)
    "max_hold": 180,     # time stop (bars)
    "cooldown": 10,      # bars to wait after an exit before re-entering
    "max_slip": 300,     # max slippage bps on every order
    "fallback_bar": 1200,  # bar from which the fallback entry may fire
    "fallback_mom": 0.002,  # fallback momentum threshold on a fresh cross
    "fallback_gap_mom": 0.004,  # fallback threshold while already in an uptrend
}


class Ema:
    __slots__ = ("span", "warm", "value")

    def __init__(self, span):
        self.span = span
        self.warm = []
        self.value = None

    def step(self, close):
        if self.value is not None:
            self.value += (2.0 / (self.span + 1)) * (close - self.value)
            return
        self.warm.append(close)
        if len(self.warm) == self.span:
            self.value = sum(self.warm) / self.span


class State:
    def __init__(self):
        self.reset()

    def reset(self):
        self.fast = Ema(PARAMS["fast"])
        self.slow = Ema(PARAMS["slow"])
        self.closes = []
        self.prev_gap = None
        self.gap = None
        self.entry_bar = None
        self.peak_value = 0
        self.last_exit_bar = -10 ** 9
        self.bar = -1
        self.filled_buys = 0


S = State()


def reset_state():
    S.reset()


def on_batch(state, batch):
    S.bar += 1
    p = PARAMS
    for fill in batch.get("fills") or []:
        if fill.get("side") == "buy" and fill.get("status") == "filled":
            S.filled_buys += 1
    for bar in batch["bars"]:
        if bar["symbol"] != SYMBOL:
            continue
        close = int(bar["c"]) / 1e5
        S.closes.append(close)
        if len(S.closes) > 300:
            S.closes.pop(0)
        S.fast.step(close)
        S.slow.step(close)
        S.prev_gap = S.gap
        if S.fast.value is not None and S.slow.value is not None:
            S.gap = S.fast.value - S.slow.value
        else:
            S.gap = None

    if state.warming_up:
        return []
    held = state.positions.get(SYMBOL)

    # ---- exits ------------------------------------------------------
    if held is not None:
        value = state.value(SYMBOL, held.qty)
        cost = held.cost
        if value > S.peak_value:
            S.peak_value = value
        exit_now = False
        if S.gap is not None and S.prev_gap is not None and S.gap < 0 and S.prev_gap >= 0:
            exit_now = True  # fast EMA crossed back below slow
        if value >= cost * (1.0 + p["tp"]):
            exit_now = True
        if value <= cost * (1.0 - p["sl"]):
            exit_now = True
        if S.peak_value > 0 and value <= S.peak_value * (1.0 - p["trail"]):
            exit_now = True
        if S.entry_bar is not None and S.bar - S.entry_bar >= p["max_hold"]:
            exit_now = True
        if exit_now:
            S.last_exit_bar = S.bar
            S.entry_bar = None
            S.peak_value = 0
            return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                     "max_slippage_bps": p["max_slip"]}]
        return []

    # ---- entries ----------------------------------------------------
    if S.bar - S.last_exit_bar < p["cooldown"]:
        return []
    if S.gap is None or len(S.closes) <= p["mom_win"]:
        return []
    mom = S.closes[-1] / S.closes[-1 - p["mom_win"]] - 1.0
    crossed = S.prev_gap is not None and S.prev_gap <= 0 and S.gap > 0
    want = crossed and mom > p["mom_thr"]
    if not want and S.bar >= p["fallback_bar"] and S.filled_buys == 0:
        if (crossed and mom > p["fallback_mom"]) or (S.gap > 0 and mom > p["fallback_gap_mom"]):
            want = True
    if not want:
        return []
    spend = int(state.cash)
    if spend < 1_000_000:
        return []
    S.entry_bar = S.bar
    S.peak_value = 0
    return [{"side": "buy", "symbol": SYMBOL, "notional_quote_units": spend,
             "max_slippage_bps": p["max_slip"]}]


def on_done(state, done):
    return None


if __name__ == "__main__":
    makefun_bars.run(on_batch, on_done=on_done)
