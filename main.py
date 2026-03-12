import os
import time
import logging
import requests
from datetime import datetime
from agent import PolymarketAgent

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    logger.info("🚀 Iniciando Polymarket Agent...")
    
    # Configuración desde variables de entorno
    config = {
        "private_key": os.getenv("WALLET_PRIVATE_KEY"),
        "telegram_token": os.getenv("TELEGRAM_BOT_TOKEN"),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID"),
        "simulation_mode": os.getenv("SIMULATION_MODE", "true").lower() == "true",
        "max_bet_usdc": float(os.getenv("MAX_BET_USDC", "1.0")),
        "min_consensus": int(os.getenv("MIN_CONSENSUS_WALLETS", "4")),
        "top_wallets_count": int(os.getenv("TOP_WALLETS_COUNT", "10")),
        "check_interval_seconds": int(os.getenv("CHECK_INTERVAL_SECONDS", "300")),
    }

    if not config["private_key"] and not config["simulation_mode"]:
        logger.error("❌ WALLET_PRIVATE_KEY no configurada. Activa SIMULATION_MODE=true o agrega la clave.")
        return

    agent = PolymarketAgent(config)
    
    logger.info(f"✅ Modo: {'SIMULACIÓN' if config['simulation_mode'] else '🔴 REAL'}")
    logger.info(f"💰 Apuesta máxima: ${config['max_bet_usdc']} USDC")
    logger.info(f"🔁 Revisando cada {config['check_interval_seconds']}s")

    while True:
        try:
            agent.run_cycle()
            time.sleep(config["check_interval_seconds"])
        except KeyboardInterrupt:
            logger.info("⛔ Agente detenido manualmente.")
            break
        except Exception as e:
            logger.error(f"❌ Error en ciclo: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
