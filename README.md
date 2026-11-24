# guardrail

**Risk limits for people who let an AI agent trade their money.**

Agents are easy to build and easy to make dangerous. Most "autonomous trader" demos have exactly one
thing in the loop: the model. It has no memory of the last loss, no concept of position sizing, and no
way to stop itself at 3am.

`guardrail` is the wall between an agent and your exchange account. Every proposed order is gated by
code the agent cannot argue with:

```python
from guardrail import Policy, AccountState, Order, check_order

verdict = check_order(Policy(), account, Order("SOL", "buy", 120.0))
if not verdict:                 # deny or require_human
    log(verdict.reason)         # machine-readable: position_cap, cash_reserve, ...
```

Three outcomes, not two: `allow`, `deny`, and **`require_human`** — because some halts must never be
cleared by the thing that caused them.

## What it enforces

| Rule | Default | Why |
|---|---|---|
| max position | 20% of equity | one bad idea can't take the account |
| max daily loss (realized) | 3% | halts and escalates to a human |
| max asset exposure | 10% | no accidental single-asset bet |
| loss streak | 3 trades | stops revenge trading |
| cash reserve | 10% | always able to act |
| shorts | off by default | opt in explicitly |

Key design choice: **only realized losses halt.** A floating drawdown on a wick should not brick the
agent, but money actually lost should. The halt reason `realized_loss_halt` is human-only — the agent
gets `require_human`, never `allow`.

## Solana adapter

Read-only by design — the guard answers *may this order happen*, it never holds keys or signs.

```bash
$ python cli.py swap-check --notional 3 --equity 15.75 --cash 15.75 \
    --max-position-pct 0.35 --max-asset-pct 0.35
{
  "guard": {"decision": "allow", "reason": "ok", "detail": ""},
  "quote": {"input": "USDT", "output": "SOL", "in_amount": 3.0, "out_amount": 0.042433469,
            "rate": 0.014144489666666668, "price_impact_pct": 0.0, "slippage_bps": 50, "routes": 2}
}
```

Same command with default limits:

```bash
$ python cli.py swap-check --notional 5 --equity 15.75 --cash 15.75
{"guard": {"decision": "deny", "reason": "position_cap", "detail": "5.00 > 20% of equity"}}
```

Live pricing comes from Jupiter v6; balances from mainnet RPC. Nothing is signed or sent.

## Ledger

Every fill, fee and halt is appended to SQLite with a SHA-256 hash chain:

```bash
python cli.py verify-ledger --db guardrail.db   # ok | TAMPERED
```

A trading record you can audit beats a P&L screenshot.

## CLI

```bash
$ python cli.py policy
position≤20% equity | daily loss≤3.0% | asset≤10% | halt after 3 losses | cash reserve≥10%

$ python cli.py check --asset SOL --side buy --notional 250 --equity 1000 --cash 1000
{"decision": "deny", "reason": "position_cap", "detail": "250.00 > 20% of equity"}

$ python cli.py check --asset SOL --side buy --notional 50 --equity 1000 --cash 1000 --realized-today -40
{"decision": "require_human", "reason": "realized_loss_halt", "detail": "daily realized loss 4.00% ≥ limit 3.00%"}
```

## Tests

```
13 passed
```

Coverage: policy gates, the realized-vs-floating loss distinction, human-only halts, ledger tamper
detection, lamport conversion, and Jupiter quote parsing (offline, with a fixture).

Pure logic — no exchange credentials, no network, no SDK. Wire it into whatever broker or DEX client
you already have; the guard only needs equity, cash, positions and the order.

## Status

v0.1 — policy engine + hash-chained ledger. Solana execution adapter (Jupiter v6 quotes/swaps) and a
small dashboard land next.

MIT.
