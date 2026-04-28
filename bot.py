"""
🟢 Green Candle Bot — Ana Döngü
=================================

Mantık:
1. Her saat 1H mum kapanışına CANDLE_WATCH_WINDOW_SEC kala aktif izlemeye başlar
2. Mum kırmızıysa → yeşile çevirecek minimum alımı hesaplar
3. Alım yapar
4. Mum kapanana kadar izlemeye devam — tekrar kırmızıya dönerse yeniden alır
5. Mum kapandıktan sonra sonraki saat için uyur
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_UP

from config import (
    DAILY_BUDGET_SOL,
    MIN_BUY_SOL,
    MAX_BUY_SOL,
    CANDLE_WATCH_WINDOW_SEC,
    CHECK_INTERVAL_SEC,
    TOKEN_MINT,
)
from candle import fetch_current_candle, CandleInfo, HOUR_SECONDS
from swap import execute_buy, get_wallet_balance_sol

log = logging.getLogger("bot")

# ============ DURUM ============

class DailyBudget:
    """Günlük bütçe takibi."""

    def __init__(self, limit: Decimal):
        self.limit = limit
        self.spent = Decimal("0")
        self._day = datetime.now(timezone.utc).date()

    def _check_reset(self):
        today = datetime.now(timezone.utc).date()
        if today != self._day:
            log.info(f"Yeni gün → bütçe sıfırlandı (dünkü harcama: {self.spent} SOL)")
            self.spent = Decimal("0")
            self._day = today

    @property
    def remaining(self) -> Decimal:
        self._check_reset()
        return max(Decimal("0"), self.limit - self.spent)

    def record(self, amount: Decimal):
        self._check_reset()
        self.spent += amount
        log.info(f"Harcama kaydedildi: {amount} SOL | Günlük: {self.spent}/{self.limit}")

    @property
    def exhausted(self) -> bool:
        return self.remaining <= MIN_BUY_SOL


# ============ ALIM MİKTARI HESAPLAMA ============

def calculate_buy_amount(candle: CandleInfo) -> Decimal:
    """
    Mumu yeşile çevirecek MİNİMUM alım miktarını hesapla.

    Mantık:
    - Mum kırmızıysa → fiyatı open'ın biraz üzerine çıkaracak alım gerekli
    - Tam open'a eşitlemek yeterli değil (spread/slippage nedeniyle) → %0.1 buffer ekle
    - Küçük bir kırmızı mum → küçük alım yeterli
    - Büyük düşüş → MAX_BUY_SOL ile sınırla (büyük düşüşte savaşma)

    Pump.fun bonding curve'de alım etkisi daha büyük olduğu için
    bu hesaplama yaklaşıktır — birkaç iterasyonda düzelir.
    """
    if candle.is_green:
        return Decimal("0")

    # Fiyat farkı yüzdesi (negatif = kırmızı)
    diff_pct = abs(candle.price_diff_pct)

    # Heuristic: düşüş yüzdesiyle orantılı alım
    # Küçük düşüşler → MIN_BUY, büyük düşüşler → daha fazla ama MAX_BUY'la sınırlı
    if diff_pct < Decimal("0.5"):
        # %0.5'ten az kırmızı → minimum alım yeterli
        amount = MIN_BUY_SOL
    elif diff_pct < Decimal("2"):
        # %0.5-2 arası → kademeli artış
        ratio = diff_pct / Decimal("2")
        amount = MIN_BUY_SOL + (MAX_BUY_SOL - MIN_BUY_SOL) * ratio
    else:
        # %2'den fazla düşüş → max alım
        amount = MAX_BUY_SOL

    # Yuvarlama
    amount = amount.quantize(Decimal("0.001"), rounding=ROUND_UP)

    return min(amount, MAX_BUY_SOL)


# ============ MUM İZLEME ============

async def watch_and_fix_candle(budget: DailyBudget) -> dict:
    """
    Mevcut 1H mumun kapanışını izle ve gerekirse alım yap.

    Returns:
        İstatistik dict'i: buys, sol_spent, final_color
    """
    stats = {"buys": 0, "sol_spent": Decimal("0"), "final_color": "unknown"}

    while True:
        # Mum verisi çek
        candle = await fetch_current_candle()
        if candle is None:
            log.warning("Mum verisi alınamadı, 30s sonra tekrar denenecek...")
            await asyncio.sleep(30)
            continue

        seconds_left = candle.seconds_to_close
        log.info(
            f"Mum: {'🟢 YEŞİL' if candle.is_green else '🔴 KIRMIZI'} | "
            f"Fark: {candle.price_diff_pct:+.3f}% | "
            f"Kapanışa: {seconds_left}s | "
            f"Open: {candle.open_price:.10f} | "
            f"Current: {candle.current_price:.10f}"
        )

        # Mum zaten kapandı mı?
        if seconds_left <= 0:
            stats["final_color"] = "green" if candle.is_green else "red"
            log.info(f"Mum kapandı → {stats['final_color'].upper()}")
            break

        # İzleme penceresinde miyiz? (kapanışa X saniye kala)
        if seconds_left > CANDLE_WATCH_WINDOW_SEC:
            # Henüz izleme penceresi değil — uyu
            sleep_time = seconds_left - CANDLE_WATCH_WINDOW_SEC
            log.info(f"İzleme penceresine {sleep_time}s kaldı, bekleniyor...")
            await asyncio.sleep(min(sleep_time, 60))
            continue

        # İZLEME PENCERESİNDEYİZ
        if candle.is_green:
            # Mum yeşil — sadece izle, alım gerekmiyor
            log.info("Mum yeşil, alım gerekmiyor. İzlemeye devam...")
            await asyncio.sleep(CHECK_INTERVAL_SEC)
            continue

        # 🔴 MUM KIRMIZI — ALIM YAP
        if budget.exhausted:
            log.warning("Günlük bütçe tükendi! Alım yapılamıyor.")
            await asyncio.sleep(CHECK_INTERVAL_SEC)
            continue

        buy_amount = calculate_buy_amount(candle)
        buy_amount = min(buy_amount, budget.remaining)

        if buy_amount < MIN_BUY_SOL:
            log.warning(f"Hesaplanan alım ({buy_amount}) minimum altında, skip")
            await asyncio.sleep(CHECK_INTERVAL_SEC)
            continue

        log.info(
            f"🛒 ALIM KARARI: {buy_amount} SOL | "
            f"Sebep: Mum kırmızı ({candle.price_diff_pct:+.3f}%), "
            f"kapanışa {seconds_left}s kaldı"
        )

        result = await execute_buy(buy_amount)

        if result.get("success"):
            stats["buys"] += 1
            stats["sol_spent"] += buy_amount
            budget.record(buy_amount)
            log.info(
                f"✅ Alım başarılı: {buy_amount} SOL | "
                f"TX: {result.get('signature', 'N/A')}"
            )

            # Alım sonrası fiyat güncellensin diye kısa bekle
            await asyncio.sleep(5)
        else:
            log.error(f"❌ Alım başarısız: {result.get('error', 'bilinmeyen hata')}")
            await asyncio.sleep(CHECK_INTERVAL_SEC)
            continue

        # Kapanışa çok az kaldıysa daha sık kontrol
        if seconds_left <= 30:
            await asyncio.sleep(3)
        elif seconds_left <= 60:
            await asyncio.sleep(5)
        else:
            await asyncio.sleep(CHECK_INTERVAL_SEC)

    return stats


# ============ ANA DÖNGÜ ============

async def main():
    log.info("=" * 60)
    log.info("🟢 Green Candle Bot başlatıldı")
    log.info(f"Token: {TOKEN_MINT}")
    log.info(f"Günlük bütçe: {DAILY_BUDGET_SOL} SOL")
    log.info(f"Alım aralığı: {MIN_BUY_SOL} - {MAX_BUY_SOL} SOL")
    log.info(f"İzleme penceresi: kapanıştan {CANDLE_WATCH_WINDOW_SEC}s önce")
    log.info("=" * 60)

    # Bakiye kontrol
    balance = await get_wallet_balance_sol()
    log.info(f"Cüzdan bakiyesi: {balance} SOL")
    if balance < MIN_BUY_SOL + Decimal("0.01"):
        log.error("Yetersiz bakiye! Bot durduruluyor.")
        return

    budget = DailyBudget(DAILY_BUDGET_SOL)

    cycle = 0
    while True:
        cycle += 1
        log.info(f"\n{'='*40} Cycle #{cycle} {'='*40}")

        try:
            stats = await watch_and_fix_candle(budget)

            log.info(
                f"Mum sonucu: {stats['final_color'].upper()} | "
                f"Alım sayısı: {stats['buys']} | "
                f"Harcanan: {stats['sol_spent']} SOL | "
                f"Günlük kalan: {budget.remaining} SOL"
            )

        except KeyboardInterrupt:
            log.info("Bot kullanıcı tarafından durduruldu.")
            break
        except Exception as e:
            log.error(f"Beklenmeyen hata: {e}", exc_info=True)
            await asyncio.sleep(30)

        # Sonraki mumun izleme penceresine kadar bekle
        now = int(time.time())
        current_candle_end = now - (now % HOUR_SECONDS) + HOUR_SECONDS
        next_watch_start = current_candle_end + HOUR_SECONDS - CANDLE_WATCH_WINDOW_SEC
        sleep_duration = max(10, next_watch_start - now)

        log.info(f"Sonraki izleme: {sleep_duration}s sonra (~{sleep_duration // 60} dakika)")
        await asyncio.sleep(sleep_duration)


if __name__ == "__main__":
    asyncio.run(main())
