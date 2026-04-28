"""
Mum Verisi Modülü
==================
1 saatlik mum verisini çeker. Birden fazla kaynak destekler:
- Birdeye API (ücretsiz tier)
- DexScreener API
- Jupiter Price API (fallback)

Mevcut mumun open/close fiyatını belirler ve kırmızı mı yeşil mi olduğunu hesaplar.
"""

import time
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import httpx

from config import TOKEN_MINT

log = logging.getLogger("candle")

HOUR_SECONDS = 3600


@dataclass
class CandleInfo:
    """Mevcut 1H mum bilgisi."""
    open_price: Decimal        # Mumun açılış fiyatı (SOL cinsinden)
    current_price: Decimal     # Şu anki fiyat
    candle_start_ts: int       # Mumun başladığı unix timestamp
    candle_end_ts: int         # Mumun kapanacağı unix timestamp
    is_green: bool             # current >= open ise yeşil
    seconds_to_close: int      # Kapanışa kalan saniye

    @property
    def is_red(self) -> bool:
        return not self.is_green

    @property
    def price_diff_pct(self) -> Decimal:
        """Open'dan ne kadar uzakta (yüzde)."""
        if self.open_price == 0:
            return Decimal("0")
        return ((self.current_price - self.open_price) / self.open_price) * 100


def _current_candle_boundaries() -> tuple[int, int]:
    """Şu anki 1H mum sınırlarını hesapla."""
    now = int(time.time())
    candle_start = now - (now % HOUR_SECONDS)
    candle_end = candle_start + HOUR_SECONDS
    return candle_start, candle_end


async def fetch_candle_dexscreener(token_mint: str) -> Optional[CandleInfo]:
    """
    DexScreener API'den mum verisi çek.
    Ücretsiz, API key gerektirmez.
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # DexScreener pair arama
            resp = await client.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{token_mint}"
            )
            resp.raise_for_status()
            data = resp.json()

            pairs = data.get("pairs", [])
            if not pairs:
                log.warning("DexScreener'da pair bulunamadı")
                return None

            # SOL pair'ini bul (en yüksek likidite)
            sol_pair = None
            for p in pairs:
                quote = p.get("quoteToken", {}).get("symbol", "")
                if quote == "SOL":
                    if sol_pair is None or (p.get("liquidity", {}).get("usd", 0) >
                                            sol_pair.get("liquidity", {}).get("usd", 0)):
                        sol_pair = p

            if not sol_pair:
                sol_pair = pairs[0]

            current_price = Decimal(str(sol_pair.get("priceNative", "0")))

            # 1H price change kullanarak open price hesapla
            price_change_1h = sol_pair.get("priceChange", {}).get("h1", 0)
            if price_change_1h is not None and price_change_1h != 0:
                change_factor = Decimal("1") + Decimal(str(price_change_1h)) / Decimal("100")
                open_price = current_price / change_factor
            else:
                open_price = current_price

            candle_start, candle_end = _current_candle_boundaries()
            now = int(time.time())

            return CandleInfo(
                open_price=open_price,
                current_price=current_price,
                candle_start_ts=candle_start,
                candle_end_ts=candle_end,
                is_green=current_price >= open_price,
                seconds_to_close=candle_end - now,
            )

    except Exception as e:
        log.error(f"DexScreener hatası: {e}")
        return None


async def fetch_candle_birdeye(token_mint: str) -> Optional[CandleInfo]:
    """
    Birdeye API'den gerçek OHLCV mum verisi çek.
    Not: Birdeye ücretsiz tier sınırlıdır ama 1H mum destekler.
    """
    try:
        candle_start, candle_end = _current_candle_boundaries()
        now = int(time.time())

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://public-api.birdeye.so/defi/ohlcv",
                params={
                    "address": token_mint,
                    "type": "1H",
                    "time_from": candle_start - HOUR_SECONDS,
                    "time_to": now,
                },
                headers={
                    "accept": "application/json",
                    # Birdeye ücretsiz tier — API key opsiyonel ama rate limit düşük
                },
            )
            resp.raise_for_status()
            data = resp.json()

            items = data.get("data", {}).get("items", [])
            if not items:
                return None

            # En son mum
            latest = items[-1]
            open_price = Decimal(str(latest.get("o", 0)))
            close_price = Decimal(str(latest.get("c", 0)))

            # Bu mum hala açık mı kontrol
            candle_ts = int(latest.get("unixTime", 0))
            if candle_ts >= candle_start:
                current_price = close_price
            else:
                # Eski mum — current price için ayrı çağrı
                price_resp = await client.get(
                    "https://public-api.birdeye.so/defi/price",
                    params={"address": token_mint},
                )
                price_data = price_resp.json()
                current_price = Decimal(str(price_data.get("data", {}).get("value", close_price)))
                open_price = close_price  # Fallback

            return CandleInfo(
                open_price=open_price,
                current_price=current_price,
                candle_start_ts=candle_start,
                candle_end_ts=candle_end,
                is_green=current_price >= open_price,
                seconds_to_close=candle_end - now,
            )

    except Exception as e:
        log.error(f"Birdeye hatası: {e}")
        return None


async def fetch_current_candle() -> Optional[CandleInfo]:
    """
    Mevcut 1H mum verisini çek. Birden fazla kaynak dener.
    """
    # Önce DexScreener (daha güvenilir, API key gerektirmez)
    candle = await fetch_candle_dexscreener(TOKEN_MINT)
    if candle:
        return candle

    # Fallback: Birdeye
    candle = await fetch_candle_birdeye(TOKEN_MINT)
    if candle:
        return candle

    log.error("Hiçbir kaynaktan mum verisi alınamadı!")
    return None
