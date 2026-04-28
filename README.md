# 🟢 Pump.fun / Raydium Green Candle Bot

Monitors 1-hour candles for your own token. If a candle is about to close red, it automatically places the minimum buy needed to flip it green before close.

## Features

- Works for both **Pump.fun bonding curve** and **Raydium (graduated)** tokens
- Watches the last 2 minutes before each 1H candle close
- Places the minimum buy needed to turn a red candle green
- If the candle flips back to red before close, it buys again
- Daily budget limit — protects your wallet
- Detailed logging

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create your .env file
cp .env.example .env
# Edit .env — add your private key and token mint address

# 3. Run
python bot.py
```

## .env Configuration

| Variable | Description | Default |
|---|---|---|
| `WALLET_PRIVATE_KEY` | Wallet private key (base58) | **required** |
| `TOKEN_MINT` | Token mint address | **required** |
| `RPC_URL` | Solana RPC endpoint | mainnet |
| `DAILY_BUDGET_SOL` | Max daily spend | 50 |
| `MIN_BUY_SOL` | Minimum single buy | 0.002 |
| `MAX_BUY_SOL` | Maximum single buy | 20 |
| `SLIPPAGE_BPS` | Slippage tolerance (bps) | 500 |
| `PRIORITY_FEE` | Priority fee (lamports) | 100000 |
| `CHECK_INTERVAL_SEC` | Candle check interval (seconds) | 10 |
| `CANDLE_WATCH_WINDOW_SEC` | Watch window before close (seconds) | 120 |
| `TOKEN_STAGE` | `pumpfun` or `raydium` | pumpfun |

## How It Works

1. Bot calculates when the current 1H candle closes
2. Enters watch mode 2 minutes before close
3. If the candle is red → calculates the minimum buy to flip it green
4. Executes the buy
5. Keeps watching until close — if it turns red again, buys again
6. After close, sleeps until the next candle's watch window

## Security

- Never share your private key
- Use a dedicated wallet with only the funds you need for the bot
- Use a private RPC endpoint (Helius, QuickNode, etc.) — public RPC will rate limit you
- Always test with small amounts first
