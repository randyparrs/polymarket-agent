import logging
from typing import Dict
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
        self.cycle_count = 0
        self.last_market_id = None

    def run_cycle(self):
        self.cycle_count += 1
        logger.info(f"🔄 Ciclo #{self.cycle_count} iniciado")

        # 1. Obtener el mercado BTC 5min activo ahora mismo
        market = self.api.get_current_btc5min_market()

        if not market:
            logger.warning("⚠️ No se encontró mercado BTC 5min activo. Reintentando...")
            return

        condition_id = market.get("conditionId") or market.get("condition_id") or market.get("id")
        question = market.get("question", "Bitcoin Up or Down - 5 Minutes")

        logger.info(f"🔶 Mercado activo: {question}")
        logger.info(f"   ID: {condition_id}")

        # Evitar operar en el mismo mercado dos veces
        if condition_id == self.last_market_id:
            logger.info("⏭️ Mismo mercado que el ciclo anterior, esperando el siguiente...")
            return

        # 2. Obtener top wallets
        top_wallets = self.tracker.get_top_wallets(self.config["top_wallets_count"])
        if not top_wallets:
            logger.warning("⚠️ No se pudieron obtener wallets.")
            return

        # 3. Obtener traders activos en este mercado directamente
        active_traders = self.api.get_active_traders_in_market(condition_id, limit=100)
        if active_traders:
            logger.info(f"👥 {len(active_traders)} traders activos en este mercado")
            # Combinar con top wallets, priorizando los activos en el mercado
            combined = list(dict.fromkeys(active_traders + top_wallets))[:30]
        else:
            combined = top_wallets

        # 4. Analizar consenso en este mercado
        signal = self.tracker.get_btc5min_signal(
            combined,
            condition_id,
            min_consensus=self.config["min_consensus"]
        )

        if not signal:
            return

        # 4. Ejecutar o simular apuesta
        self.last_market_id = condition_id

        if self.config["simulation_mode"]:
            self._simulate_bet(signal, question, market)
        else:
            self._execute_bet(signal, question, market)

    def _simulate_bet(self, signal: Dict, question: str, market: Dict):
        direction = signal["direction"]
        bet = self.config["max_bet_usdc"]

        msg = (
            f"🟡 [SIMULACIÓN] Bitcoin 5 Min\n"
            f"📋 {question}\n"
            f"{'🟢' if direction == 'Up' else '🔴'} Dirección: {direction}\n"
            f"👥 Consenso: {signal['consensus_count']}/{self.config['top_wallets_count']} wallets ({signal['confidence_pct']:.1f}%)\n"
            f"📊 Up: {signal['up_votes']} | Down: {signal['down_votes']}\n"
            f"💵 Apuesta simulada: ${bet} USDC"
        )
        logger.info(msg)
        self.notifier.send(msg)

    def _execute_bet(self, signal: Dict, question: str, market: Dict):
        try:
            from py_clob_client.client import ClobClient

            direction = signal["direction"]
            bet = self.config["max_bet_usdc"]

            # Encontrar el token correcto (Up o Down)
            tokens = market.get("tokens", [])
            token_id = None
            for token in tokens:
                if direction.lower() in str(token.get("outcome", "")).lower():
                    token_id = token.get("token_id")
                    break

            if not token_id:
                logger.error(f"❌ No se encontró token para {direction}")
                return

            client = ClobClient(
                host="https://clob.polymarket.com",
                key=self.config["private_key"],
                chain_id=137
            )

            order_args = {
                "token_id": token_id,
                "price": 0.52 if direction == "Up" else 0.50,
                "size": bet,
                "side": "BUY"
            }

            signed_order = client.create_order(order_args)
            response = client.post_order(signed_order)

            msg = (
                f"🟢 [REAL] Apuesta ejecutada\n"
                f"{'🟢' if direction == 'Up' else '🔴'} Bitcoin 5Min: {direction}\n"
                f"💵 ${bet} USDC\n"
                f"👥 Consenso: {signal['consensus_count']} wallets\n"
                f"🔗 Order: {response.get('orderID', 'N/A')}"
            )
            logger.info(msg)
            self.notifier.send(msg)

        except Exception as e:
            error_msg = f"❌ Error ejecutando apuesta: {e}"
            logger.error(error_msg)
            self.notifier.send(error_msg)
