"""
Konfigürasyon — .env'den yüklenen tüm ayarlar burada.
"""

import os
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(f".env dosyasında {key} tanımlı değil!")
    return val


# Zorunlu
WALLET_PRIVATE_KEY: str = _require("WALLET_PRIVATE_KEY")
TOKEN_MINT: str = _require("TOKEN_MINT")

# RPC
RPC_URL: str = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")

# Bütçe
DAILY_BUDGET_SOL: Decimal = Decimal(os.getenv("DAILY_BUDGET_SOL", "50"))
MIN_BUY_SOL: Decimal = Decimal(os.getenv("MIN_BUY_SOL", "0.002"))
MAX_BUY_SOL: Decimal = Decimal(os.getenv("MAX_BUY_SOL", "20"))

# Swap
SLIPPAGE_BPS: int = int(os.getenv("SLIPPAGE_BPS", "500"))
PRIORITY_FEE: int = int(os.getenv("PRIORITY_FEE", "100000"))

# Zamanlama
CANDLE_WATCH_WINDOW_SEC: int = int(os.getenv("CANDLE_WATCH_WINDOW_SEC", "120"))
CHECK_INTERVAL_SEC: int = int(os.getenv("CHECK_INTERVAL_SEC", "10"))

# Token aşaması
TOKEN_STAGE: str = os.getenv("TOKEN_STAGE", "pumpfun").lower()
assert TOKEN_STAGE in ("pumpfun", "raydium"), "TOKEN_STAGE 'pumpfun' veya 'raydium' olmalı"

# Sabitler
SOL_MINT = "So11111111111111111111111111111111111111112"
SOL_DECIMALS = 9
LAMPORTS_PER_SOL = 1_000_000_000
