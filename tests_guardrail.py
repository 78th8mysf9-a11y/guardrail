import os, tempfile
from guardrail import Policy, AccountState, Order, check_order, Ledger, summary

def acct(**kw):
    base = dict(equity_usdt=1000.0, cash_usdt=1000.0)
    base.update(kw)
    return AccountState(**base)

def test_allow_normal_buy():
    v = check_order(Policy(), acct(), Order("SOL", "buy", 100))
    assert v.decision == "allow", v

def test_position_cap():
    v = check_order(Policy(), acct(), Order("SOL", "buy", 250))
    assert v.decision == "deny" and v.reason == "position_cap", v

def test_cash_reserve():
    v = check_order(Policy(), acct(cash_usdt=150), Order("SOL", "buy", 120))
    assert v.decision == "deny" and v.reason == "cash_reserve", v

def test_asset_cap():
    a = acct(open_positions={"SOL": 80.0})
    v = check_order(Policy(), a, Order("SOL", "buy", 50))
    assert v.decision == "deny" and v.reason == "asset_cap", v

def test_short_blocked():
    v = check_order(Policy(), acct(), Order("SOL", "sell", 50))
    assert v.decision == "deny" and v.reason == "short_not_allowed", v

def test_realized_loss_halt_is_human_only():
    a = acct(realized_pnl_today=-40.0)
    v = check_order(Policy(), a, Order("SOL", "buy", 50))
    assert v.decision == "require_human" and v.reason == "realized_loss_halt", v

def test_floating_loss_does_not_halt():
    a = acct(realized_pnl_today=0.0)
    v = check_order(Policy(), a, Order("SOL", "buy", 50))
    assert v.decision == "allow", v

def test_loss_streak_denies():
    a = acct(consecutive_losses=3)
    v = check_order(Policy(), a, Order("SOL", "buy", 50))
    assert v.decision == "deny" and v.reason == "loss_streak_halt", v

def test_human_halt_blocks_agent():
    a = acct(halted=True, halt_reason="realized_loss_halt")
    v = check_order(Policy(), a, Order("SOL", "buy", 10))
    assert v.decision == "require_human", v

def test_ledger_hash_chain_detects_tampering():
    with tempfile.TemporaryDirectory() as d:
        L = Ledger(os.path.join(d, "t.db"))
        L.append("trade", asset="SOL", qty=0.5, px=70.0)
        L.append("halt", reason="realized_loss_halt")
        assert L.verify()
        L.db.execute("UPDATE entries SET payload='{\"asset\": \"SOL\", \"px\": 999.0, \"qty\": 0.5}' WHERE id=1")
        L.db.commit()
        assert not L.verify()

def test_summary():
    assert "position" in summary(Policy())
