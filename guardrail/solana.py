"""Solana adapter: read balances over RPC, price a proposed swap with Jupiter.

No keys, no signing, no sends — this module only *looks*. Execution stays outside the guard on
purpose: the guard's job is to answer "may this order happen", not to hold custody.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

RPC_URL = "https://api.mainnet-beta.solana.com"
JUP_QUOTE = "https://lite-api.jup.ag/swap/v1/quote"

# 常见资产：mint 与 decimals
MINTS = {
    "SOL": ("So11111111111111111111111111111111111111112", 9),
    "USDC": ("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", 6),
    "USDT": ("Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", 6),
    "JUP": ("JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", 6),
    "BONK": ("DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", 5),
}


def _get(url: str, timeout: float = 20.0) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "guardrail/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _rpc(method: str, params: list, timeout: float = 20.0) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(RPC_URL, data=body,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "guardrail/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    if "error" in out:
        raise RuntimeError(f"rpc error: {out['error']}")
    return out["result"]


def lamports(amount: float, mint: str) -> int:
    """把人类单位换成最小单位。"""
    decimals = MINTS.get(mint.upper(), (None, 9))[1]
    return int(round(amount * 10 ** decimals))


def balance(wallet: str, mint: str = "SOL") -> float:
    """读一个地址的 SOL 或 SPL 代币余额（人类单位）。"""
    if mint.upper() == "SOL":
        res = _rpc("getBalance", [wallet])
        return res["value"] / 1e9
    mint_addr, decimals = MINTS.get(mint.upper(), (mint, 6))
    res = _rpc("getTokenAccountsByOwner", [wallet, {"mint": mint_addr}, {"encoding": "jsonParsed"}])
    total = 0.0
    for acct in res.get("value", []):
        amt = acct["account"]["data"]["parsed"]["info"]["tokenAmount"]
        total += float(amt["uiAmount"] or 0)
    return total


def quote(input_mint: str, output_mint: str, amount: float, slippage_bps: int = 50) -> dict:
    """要一份 Jupiter 报价。返回统一结构，便于 guard 用。"""
    inp = MINTS.get(input_mint.upper(), (input_mint, 9))[0]
    out = MINTS.get(output_mint.upper(), (output_mint, 9))[0]
    amount_units = lamports(amount, input_mint)
    qs = urllib.parse.urlencode({
        "inputMint": inp, "outputMint": out, "amount": amount_units,
        "slippageBps": slippage_bps, "swapMode": "ExactIn",
    })
    raw = _get(f"{JUP_QUOTE}?{qs}")
    in_dec = MINTS.get(input_mint.upper(), (None, 9))[1]
    out_dec = MINTS.get(output_mint.upper(), (None, 6))[1]
    in_amt = int(raw["inAmount"]) / 10 ** in_dec
    out_amt = int(raw["outAmount"]) / 10 ** out_dec
    price_impact = float(raw.get("priceImpactPct") or 0)
    return {
        "input": input_mint.upper(), "output": output_mint.upper(),
        "in_amount": in_amt, "out_amount": out_amt,
        "rate": (out_amt / in_amt) if in_amt else None,
        "price_impact_pct": price_impact,
        "slippage_bps": slippage_bps,
        "routes": len(raw.get("routePlan") or []),
        "raw": raw,
    }
