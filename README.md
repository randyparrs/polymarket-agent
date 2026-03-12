# 🤖 Polymarket Agent

Agente que copia las apuestas de las top 10 wallets en Polymarket.

## Archivos del proyecto

| Archivo | Qué hace |
|---|---|
| `main.py` | Punto de entrada, arranca el agente |
| `agent.py` | Lógica principal, decide qué apostar |
| `polymarket_api.py` | Conexión con la API de Polymarket |
| `wallet_tracker.py` | Analiza las top wallets y detecta consenso |
| `telegram_bot.py` | Envía notificaciones a tu Telegram |
| `requirements.txt` | Librerías necesarias |
| `railway.toml` | Configuración para Railway |

## Variables de entorno (configurar en Railway)

| Variable | Descripción | Requerida |
|---|---|---|
| `SIMULATION_MODE` | `true` = solo simula, `false` = apuesta real | Sí |
| `MAX_BET_USDC` | Máximo por apuesta (ej: `1.0`) | Sí |
| `MIN_CONSENSUS_WALLETS` | Mínimo wallets en acuerdo (ej: `4`) | Sí |
| `TOP_WALLETS_COUNT` | Cuántas wallets seguir (ej: `10`) | Sí |
| `CHECK_INTERVAL_SECONDS` | Frecuencia de revisión (ej: `300`) | Sí |
| `WALLET_PRIVATE_KEY` | Clave privada de tu wallet | Solo modo real |
| `TELEGRAM_BOT_TOKEN` | Token de tu bot de Telegram | Opcional |
| `TELEGRAM_CHAT_ID` | Tu chat ID de Telegram | Opcional |

## ⚠️ Importante

- Empieza siempre con `SIMULATION_MODE=true`
- Nunca subas tu `.env` a GitHub
- Usa una wallet separada solo para el agente
