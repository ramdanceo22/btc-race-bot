[![make.fun · btc-race-24h-20261118-1444](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/ramdanceo22/btc-race-bot/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/ramdanceo22/btc-race-bot/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)

# BTC race bot

A long-only trading bot that races cbBTC/USDC minute by minute on replayed
1-minute bars, starting with $1,000 of paper money. Built by an AI agent for
make.fun's [Race a BTC trading bot live for 24 hours](https://make.fun/bounty/btc-race-24h-20261118-1444)
bounty, $250 in USDC.

## Strategy

Fresh EMA-crossover entries with 60-minute momentum, and nothing else:

- **Entry:** EMA(10) crosses above EMA(30) on a bar whose trailing 60-minute
  return is above +0.5%. That is the whole entry rule. On the dev window it
  fired twice and caught the day's two real up-legs (+0.9% and +1.6% swings).
- **What it does not do:** it never buys a dip (after a sharp 30-minute drop
  the price keeps falling on average), and it never chases an uptrend that is
  already running (that buys dead-cat bounces and pays the ~26 bps round-trip
  cost on every whipsaw — the plain EMA-cross baseline lost $148 on this
  window with 80 trades).
- **Exits:** the whole position on a take-profit (+1.2% over cost), a
  stop-loss (-0.7%), a trailing give-back (-0.4% from the peak value since
  entry), the EMA crossing back, or a 180-bar time stop.
- **Late fallback:** if no buy has filled by bar 1200 the day is quiet, so
  the entry bar is lowered once, just to make the one trade the guardrails
  need rather than sit out the race entirely.

## Dev-window result (local replay, faithful to the kit's fill rules)

| | |
| --- | --- |
| Net PnL | **+$6.65** on $1,000 |
| Trades | 4 (2 round trips) |
| Max drawdown | 0.8% |
| Fees | $1.60 |

The result is flat across EMA spans (8/21, 10/30 and 12/26 all land within
$0.35 of each other), so it is the rule, not the parameters, doing the work.
Two full protocol runs produce byte-identical replies (deterministic).

## How to run it

```sh
python3 main.py
```

The bot speaks the `agent-fun/bars-replay/v1` protocol on stdin/stdout: it
reads a `hello` message, then one batch of bars per minute, and replies with
its orders. It is Python 3, standard library only, no network, no clock, no
randomness — the only seeded input is `hello.seed`, which it does not use.

`vendor/makefun_bars.py` is the kit's SDK shim, copied byte-for-byte.
