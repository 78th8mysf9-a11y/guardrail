#!/usr/bin/env python3
"""guardrail — 让 AI 交易代理撞得到的墙。"""
from __future__ import annotations

import argparse
import json
import sys

from guardrail import AccountState, Ledger, Order, Policy, check_order, summary
from guardrail.solana import quote


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="guardrail", description="risk limits for autonomous trading agents")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="gate one proposed order")
    c.add_argument("--asset", required=True)
    c.add_argument("--side", choices=["buy", "sell"], required=True)
    c.add_argument("--notional", type=float, required=True, help="order size in quote currency")
    c.add_argument("--equity", type=float, required=True)
    c.add_argument("--cash", type=float, required=True)
    c.add_argument("--realized-today", type=float, default=0.0)
    c.add_argument("--loss-streak", type=int, default=0)
    c.add_argument("--position-json", default="{}", help='{"SOL": 120.0}')
    c.add_argument("--max-position-pct", type=float, default=0.20)

    sub.add_parser("policy", help="print the active policy summary")

    v = sub.add_parser("verify-ledger", help="check the hash chain of a ledger file")
    v.add_argument("--db", default="guardrail.db")

    sw = sub.add_parser("swap-check", help="gate a proposed swap, then price it with Jupiter")
    sw.add_argument("--from-asset", default="USDT")
    sw.add_argument("--max-position-pct", type=float, default=0.20)
    sw.add_argument("--max-asset-pct", type=float, default=0.10)
    sw.add_argument("--to-asset", default="SOL")
    sw.add_argument("--notional", type=float, required=True)
    sw.add_argument("--equity", type=float, required=True)
    sw.add_argument("--cash", type=float, required=True)
    sw.add_argument("--realized-today", type=float, default=0.0)

    args = ap.parse_args(argv)

    if args.cmd == "swap-check":
        policy = Policy(max_position_pct=args.max_position_pct, max_asset_pct=args.max_asset_pct)
        acct = AccountState(equity_usdt=args.equity, cash_usdt=args.cash,
                            realized_pnl_today=args.realized_today)
        verdict = check_order(policy, acct, Order(args.to_asset, "buy", args.notional))
        out = {"guard": {"decision": verdict.decision, "reason": verdict.reason,
                         "detail": verdict.detail}}
        if verdict.decision == "allow":
            q = quote(args.from_asset, args.to_asset, args.notional)
            out["quote"] = {k: v for k, v in q.items() if k != "raw"}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if verdict.decision == "allow" else 1

    if args.cmd == "policy":
        print(summary(Policy()))
        return 0

    if args.cmd == "verify-ledger":
        print("ok" if Ledger(args.db).verify() else "TAMPERED")
        return 0

    policy = Policy(max_position_pct=args.max_position_pct)
    acct = AccountState(
        equity_usdt=args.equity,
        cash_usdt=args.cash,
        realized_pnl_today=args.realized_today,
        consecutive_losses=args.loss_streak,
        open_positions=json.loads(args.position_json),
    )
    verdict = check_order(policy, acct, Order(args.asset, args.side, args.notional))
    print(json.dumps({"decision": verdict.decision, "reason": verdict.reason,
                      "detail": verdict.detail}, ensure_ascii=False))
    return 0 if verdict.decision == "allow" else 1


if __name__ == "__main__":
    sys.exit(main())
