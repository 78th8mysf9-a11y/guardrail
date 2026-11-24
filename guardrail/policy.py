"""Policy loading + order gating. No network, no exchange SDK — pure logic, fully testable."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Literal

Decision = Literal["allow", "deny", "require_human"]


@dataclass
class Policy:
    max_position_pct: float = 0.20      # 单仓占净值上限
    max_daily_loss_pct: float = 0.03    # 当日已实现亏损上限
    max_asset_pct: float = 0.10         # 单资产敞口上限
    loss_streak_halt: int = 3           # 连亏 N 笔 → 停机
    cooldown_minutes: int = 60          # 停机后冷却
    min_cash_reserve_pct: float = 0.10  # 现金最低留存
    allow_short: bool = False
    human_only_reasons: tuple[str, ...] = ("realized_loss_halt", "manual_halt")


@dataclass
class AccountState:
    equity_usdt: float
    cash_usdt: float
    realized_pnl_today: float = 0.0
    consecutive_losses: int = 0
    open_positions: dict[str, float] = field(default_factory=dict)  # 资产 → 市值
    halted: bool = False
    halt_reason: str = ""


@dataclass
class Order:
    asset: str
    side: Literal["buy", "sell"]
    notional_usdt: float
    reduce_only: bool = False


@dataclass
class Verdict:
    decision: Decision
    reason: str
    detail: str = ""

    def __bool__(self) -> bool:
        return self.decision == "allow"


def check_order(policy: Policy, account: AccountState, order: Order) -> Verdict:
    """Every order must pass through here. Denials carry machine-readable reason codes."""
    p, a = policy, account

    if a.halted:
        human = a.halt_reason in p.human_only_reasons
        return Verdict("require_human" if human else "deny", a.halt_reason,
                       "halt is active; agent may not clear a human-only halt")

    if order.notional_usdt <= 0:
        return Verdict("deny", "invalid_notional")

    if order.side == "sell" and not order.reduce_only and not p.allow_short:
        return Verdict("deny", "short_not_allowed")

    # 当日亏损上限：只认已实现亏损，浮亏不触发（否则一个插针就停机）
    if a.realized_pnl_today < 0:
        loss_pct = -a.realized_pnl_today / max(a.equity_usdt, 1e-9)
        if loss_pct >= p.max_daily_loss_pct:
            return Verdict("require_human", "realized_loss_halt",
                           f"daily realized loss {loss_pct:.2%} ≥ limit {p.max_daily_loss_pct:.2%}")

    if a.consecutive_losses >= p.loss_streak_halt:
        return Verdict("deny", "loss_streak_halt", f"{a.consecutive_losses} consecutive losses")

    if order.side == "buy":
        if order.notional_usdt > a.equity_usdt * p.max_position_pct:
            return Verdict("deny", "position_cap",
                           f"{order.notional_usdt:.2f} > {p.max_position_pct:.0%} of equity")
        if a.cash_usdt - order.notional_usdt < a.equity_usdt * p.min_cash_reserve_pct:
            return Verdict("deny", "cash_reserve",
                           "order would breach minimum cash reserve")
        new_exposure = a.open_positions.get(order.asset, 0.0) + order.notional_usdt
        if new_exposure > a.equity_usdt * p.max_asset_pct:
            return Verdict("deny", "asset_cap",
                           f"{order.asset} exposure {new_exposure:.2f} > {p.max_asset_pct:.0%}")

    return Verdict("allow", "ok")


def summary(policy: Policy) -> str:
    return (f"position≤{policy.max_position_pct:.0%} equity | daily loss≤{policy.max_daily_loss_pct:.1%} "
            f"| asset≤{policy.max_asset_pct:.0%} | halt after {policy.loss_streak_halt} losses "
            f"| cash reserve≥{policy.min_cash_reserve_pct:.0%}")
