# 🟢 Pump.fun / Raydium Green Candle Bot

Kendi token'ın için 1 saatlik mumları izler. Mum kırmızı kapanacaksa, kapanıştan önce minimum alım yaparak yeşile çevirir.

## Özellikler

- **Pump.fun bonding curve** ve **Raydium (graduated)** tokenler için çalışır
- 1 saatlik mum kapanışına yakın (son 2 dakika) kontrol eder
- Kırmızı kapanacaksa minimum yeşile çevirecek kadar alım yapar
- Mum kapanışına kadar tekrar kırmızıya dönerse yeniden alım
- Günlük bütçe limiti — cüzdanı korur
- Detaylı log'lama

## Kurulum

```bash
# 1. Bağımlılıklar
pip install -r requirements.txt

# 2. .env dosyasını oluştur
cp .env.example .env
# .env'yi düzenle, private key ve token mint adresini gir

# 3. Çalıştır
python bot.py
```

## .env Ayarları

| Değişken | Açıklama | Varsayılan |
|---|---|---|
| `WALLET_PRIVATE_KEY` | Cüzdan private key (base58) | **zorunlu** |
| `TOKEN_MINT` | Token mint adresi | **zorunlu** |
| `RPC_URL` | Solana RPC endpoint | mainnet |
| `DAILY_BUDGET_SOL` | Günlük max harcama | 0.5 |
| `MIN_BUY_SOL` | Minimum tek alım | 0.002 |
| `MAX_BUY_SOL` | Maksimum tek alım | 0.05 |
| `SLIPPAGE_BPS` | Slippage toleransı (bps) | 500 |
| `PRIORITY_FEE` | Priority fee (lamports) | 100000 |
| `CHECK_INTERVAL_SEC` | Mum izleme aralığı (saniye) | 10 |
| `CANDLE_WATCH_WINDOW_SEC` | Kapanıştan kaç sn önce izle | 120 |
| `TOKEN_STAGE` | `pumpfun` veya `raydium` | pumpfun |

## Güvenlik

- Private key'ini ASLA kimseyle paylaşma
- Önce çok küçük bütçeyle test et
- RPC olarak özel endpoint kullan (Helius, Quicknode vb.)
