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


# ---- Solana adapter（离线：只测换算与报价结构，不打网络） ----
def test_lamports_conversion():
    from guardrail.solana import lamports
    assert lamports(1, "SOL") == 1_000_000_000
    assert lamports(0.5, "USDC") == 500_000
    assert lamports(0.088580331, "SOL") == 88_580_331

def test_quote_shape_from_raw(monkeypatch_free=True):
    from guardrail import solana
    fake = {"inAmount": "3000000", "outAmount": "42433469",
            "priceImpactPct": "0.0001", "routePlan": [{}, {}]}
    orig = solana._get
    solana._get = lambda *a, **k: fake
    try:
        q = solana.quote("USDT", "SOL", 3)
        assert abs(q["in_amount"] - 3.0) < 1e-9
        assert abs(q["out_amount"] - 0.042433469) < 1e-9
        assert q["routes"] == 2
        assert q["price_impact_pct"] == 0.0001
    finally:
        solana._get = orig


def _run_all() -> int:
    import sys
    ok = fail = 0
    names = [n for n, v in list(globals().items()) if n.startswith("test_") and callable(v)]
    for name in sorted(names):
        try:
            globals()[name]()
            ok += 1
        except Exception as e:  # noqa: BLE001
            fail += 1
            print(f"FAIL {name}: {e}")
    print(f"{ok} passed, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    sys.exit(_run_all())
