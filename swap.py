"""
Swap Modülü
============
Token alımı yapar. İki yöntem:
1. Jupiter Aggregator (Raydium graduated tokenler) — en güvenilir
2. Pump.fun API (bonding curve tokenler)

Her iki durumda da SOL → Token swap yapar.
"""

import logging
from decimal import Decimal

import httpx
import base58
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

from config import (
    WALLET_PRIVATE_KEY,
    TOKEN_MINT,
    RPC_URL,
    SLIPPAGE_BPS,
    PRIORITY_FEE,
    SOL_MINT,
    LAMPORTS_PER_SOL,
    TOKEN_STAGE,
)

log = logging.getLogger("swap")

# Cüzdan
_keypair = Keypair.from_bytes(base58.b58decode(WALLET_PRIVATE_KEY))
WALLET_PUBKEY = str(_keypair.pubkey())

log.info(f"Cüzdan: {WALLET_PUBKEY}")
log.info(f"Token: {TOKEN_MINT}")
log.info(f"Aşama: {TOKEN_STAGE}")


async def get_wallet_balance_sol() -> Decimal:
    """Cüzdandaki SOL bakiyesini getir."""
    async with AsyncClient(RPC_URL) as client:
        resp = await client.get_balance(_keypair.pubkey(), commitment=Confirmed)
        lamports = resp.value
        return Decimal(str(lamports)) / Decimal(str(LAMPORTS_PER_SOL))


# ============ JUPITER SWAP (Raydium) ============

async def swap_via_jupiter(sol_amount: Decimal) -> dict:
    """
    Jupiter Aggregator ile SOL → Token swap.
    Raydium'a graduate olmuş tokenler için kullanılır.
    """
    lamports_in = int(sol_amount * LAMPORTS_PER_SOL)

    async with httpx.AsyncClient(timeout=30) as http:
        # 1. Quote al
        log.info(f"Jupiter quote alınıyor: {sol_amount} SOL → {TOKEN_MINT}")
        quote_resp = await http.get(
            "https://quote-api.jup.ag/v6/quote",
            params={
                "inputMint": SOL_MINT,
                "outputMint": TOKEN_MINT,
                "amount": str(lamports_in),
                "slippageBps": SLIPPAGE_BPS,
            },
        )
        quote_resp.raise_for_status()
        quote = quote_resp.json()

        out_amount = int(quote.get("outAmount", 0))
        log.info(f"Quote: {sol_amount} SOL → {out_amount} token (raw)")

        # 2. Swap transaction al
        swap_resp = await http.post(
            "https://quote-api.jup.ag/v6/swap",
            json={
                "quoteResponse": quote,
                "userPublicKey": WALLET_PUBKEY,
                "wrapAndUnwrapSol": True,
                "prioritizationFeeLamports": PRIORITY_FEE,
                "dynamicComputeUnitLimit": True,
            },
        )
        swap_resp.raise_for_status()
        swap_data = swap_resp.json()

        # 3. Transaction imzala ve gönder
        raw_tx = swap_data["swapTransaction"]
        tx_bytes = base58.b58decode(raw_tx) if not raw_tx.startswith("A") else \
            __import__("base64").b64decode(raw_tx)

        tx = VersionedTransaction.from_bytes(tx_bytes)
        signed_tx = VersionedTransaction(tx.message, [_keypair])

        async with AsyncClient(RPC_URL) as rpc:
            result = await rpc.send_transaction(
                signed_tx,
                opts={
                    "skip_preflight": True,
                    "preflight_commitment": "confirmed",
                    "max_retries": 3,
                },
            )
            sig = str(result.value)
            log.info(f"TX gönderildi: {sig}")

            return {
                "success": True,
                "signature": sig,
                "sol_spent": float(sol_amount),
                "tokens_received": out_amount,
                "method": "jupiter",
            }


# ============ PUMP.FUN SWAP ============

PUMP_FUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMP_FUN_API = "https://pumpportal.fun/api"


async def swap_via_pumpfun(sol_amount: Decimal) -> dict:
    """
    Pump.fun API ile SOL → Token swap.
    Bonding curve'de olan tokenler için kullanılır.

    PumpPortal API kullanır (pump.fun için yaygın swap endpoint).
    """
    lamports_in = int(sol_amount * LAMPORTS_PER_SOL)

    async with httpx.AsyncClient(timeout=30) as http:
        log.info(f"Pump.fun swap: {sol_amount} SOL → {TOKEN_MINT}")

        # PumpPortal trade API
        trade_resp = await http.post(
            f"{PUMP_FUN_API}/trade-local",
            json={
                "publicKey": WALLET_PUBKEY,
                "action": "buy",
                "mint": TOKEN_MINT,
                "amount": lamports_in,
                "denominatedInSol": "true",
                "slippage": SLIPPAGE_BPS / 100,  # PumpPortal yüzde bekler
                "priorityFee": PRIORITY_FEE / LAMPORTS_PER_SOL,  # SOL cinsinden
                "pool": "pump",
            },
        )
        trade_resp.raise_for_status()

        # Response transaction bytes olarak gelir
        tx_bytes = trade_resp.content
        tx = VersionedTransaction.from_bytes(tx_bytes)
        signed_tx = VersionedTransaction(tx.message, [_keypair])

        async with AsyncClient(RPC_URL) as rpc:
            result = await rpc.send_transaction(
                signed_tx,
                opts={
                    "skip_preflight": True,
                    "preflight_commitment": "confirmed",
                    "max_retries": 3,
                },
            )
            sig = str(result.value)
            log.info(f"Pump.fun TX gönderildi: {sig}")

            return {
                "success": True,
                "signature": sig,
                "sol_spent": float(sol_amount),
                "method": "pumpfun",
            }


# ============ ANA SWAP FONKSİYONU ============

async def execute_buy(sol_amount: Decimal) -> dict:
    """
    Token aşamasına göre doğru swap yöntemini seç ve çalıştır.
    """
    # Bakiye kontrol
    balance = await get_wallet_balance_sol()
    min_required = sol_amount + Decimal("0.01")  # TX fee için pay
    if balance < min_required:
        log.error(f"Yetersiz bakiye: {balance} SOL (gereken: {min_required})")
        return {"success": False, "error": "insufficient_balance", "balance": float(balance)}

    try:
        if TOKEN_STAGE == "raydium":
            return await swap_via_jupiter(sol_amount)
        else:
            return await swap_via_pumpfun(sol_amount)
    except Exception as e:
        log.error(f"Swap hatası: {e}")
        return {"success": False, "error": str(e)}
