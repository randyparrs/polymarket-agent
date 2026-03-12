import logging
import requests
from typing import List, Dict
from polymarket_api import PolymarketAPI
from wallet_tracker import WalletTracker
from telegram_bot import TelegramNotifier

logger = logging.getLogger(__name__)

class PolymarketAgent:
    def __init__(self, config: dict):
        self.config = config
        self.api = PolymarketAPI()
        self.tracker = WalletTracker(self.api)
        self.notifier = TelegramNotifier(
            config.get("telegram_token"),
            config.get("telegram_chat_id")
        )
        self.active_positions = {}
        self.cycle_count = 0

    def run_cycle(self):
        self.cycle_count += 1
        logger.info(f"🔄 Ciclo #{self.cycle_count} iniciado")

        # 1. Obtener top wallets
        logger.info("📊 Analizando top wallets...")
        top_wallets = self.tracker.get_top_wallets(self.config["top_wallets_count"])
        
        if not top_wallets:
            logger.warning("⚠️ No se pudieron obtener wallets. Reintentando en el próximo ciclo.")
            return

        logger.info(f"✅ Top {len(top_wallets)} wallets encontradas")

        # 2. Obtener apuestas recientes de esas wallets
        signals = self.tracker.get_consensus_signals(
            top_wallets,
            min_consensus=self.config["min_consensus"]
        )

        if not signals:
            logger.info("😴 Sin señales de consenso esta ronda.")
            return

        logger.info(f"🎯 {len(signals)} señales encontradas")

        # 3. Evaluar y ejecutar
        for signal in signals:
            self._process_signal(signal)

    def _process_signal(self, signal: Dict):
        market_id = signal["market_id"]
        
        # Evitar duplicados
        if market_id in self.active_positions:
            logger.info(f"⏭️ Ya tenemos posición en {signal['question'][:40]}...")
            return

        consensus = signal["consensus_count"]
        outcome = signal["outcome"]
        price = signal["avg_price"]
        question = signal["question"]

        # Calcular tamaño de apuesta según consenso
        bet_size = self._calculate_bet_size(consensus)

        logger.info(f"📌 Señal: {question[:50]}")
        logger.info(f"   Consenso: {consensus}/10 wallets | Outcome: {outcome} | Precio: {price:.2f}")
        logger.info(f"   Apuesta calculada: ${bet_size:.2f} USDC")

        if self.config["simulation_mode"]:
            self._simulate_bet(signal, bet_size)
        else:
            self._execute_bet(signal, bet_size)

    def _calculate_bet_size(self, consensus: int) -> float:
        max_bet = self.config["max_bet_usdc"]
        if consensus >= 8:
            return max_bet
        elif consensus >= 6:
            return max_bet * 0.7
        elif consensus >= 4:
            return max_bet * 0.4
        else:
            return max_bet * 0.2

    def _simulate_bet(self, signal: Dict, bet_size: float):
        msg = (
            f"🟡 [SIMULACIÓN] Apuesta detectada\n"
            f"📋 {signal['question'][:60]}\n"
            f"✅ Outcome: {signal['outcome']}\n"
            f"💵 Monto: ${bet_size:.2f} USDC\n"
            f"📊 Precio: {signal['avg_price']:.2f}\n"
            f"👥 Consenso: {signal['consensus_count']}/10 wallets\n"
            f"💰 Ganancia potencial: ${bet_size / signal['avg_price'] - bet_size:.2f}"
        )
        logger.info(msg)
        self.notifier.send(msg)
        self.active_positions[signal["market_id"]] = {
            "simulated": True,
            "bet_size": bet_size,
            "signal": signal
        }

    def _execute_bet(self, signal: Dict, bet_size: float):
        # Implementación real con py-clob-client
        try:
            from py_clob_client.client import ClobClient
            
            client = ClobClient(
                host="https://clob.polymarket.com",
                key=self.config["private_key"],
                chain_id=137  # Polygon
            )
            
            # Crear orden
            order_args = {
                "token_id": signal["token_id"],
                "price": signal["avg_price"],
                "size": bet_size,
                "side": "BUY"
            }
            
            signed_order = client.create_order(order_args)
            response = client.post_order(signed_order)
            
            msg = (
                f"🟢 [REAL] Apuesta ejecutada\n"
                f"📋 {signal['question'][:60]}\n"
                f"✅ Outcome: {signal['outcome']}\n"
                f"💵 Monto: ${bet_size:.2f} USDC\n"
                f"🔗 Order ID: {response.get('orderID', 'N/A')}"
            )
            logger.info(msg)
            self.notifier.send(msg)
            self.active_positions[signal["market_id"]] = {
                "simulated": False,
                "bet_size": bet_size,
                "order_id": response.get("orderID"),
                "signal": signal
            }

        except Exception as e:
            error_msg = f"❌ Error ejecutando apuesta: {e}"
            logger.error(error_msg)
            self.notifier.send(error_msg)
