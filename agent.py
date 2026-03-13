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
            from py_clob_client.clob_types import ApiCreds

            direction = signal["direction"]
            bet = self.config["max_bet_usdc"]
            private_key = self.config["private_key"]
            proxy_wallet = self.config.get("proxy_wallet", "")

            # Encontrar el token correcto (Up o Down)
            tokens = market.get("tokens", [])
            token_id = None
            price = 0.50

            for token in tokens:
                outcome = str(token.get("outcome", "") or "").lower()
                if direction.lower() in outcome:
                    token_id = token.get("token_id") or token.get("tokenId")
                    price = float(token.get("price", 0.50) or 0.50)
                    break

            if not token_id:
                # Intentar con outcomeIndex
                outcomes = market.get("outcomes", ["Up", "Down"])
                idx = 0 if direction == "Up" else 1
                tokens_list = market.get("clobTokenIds", [])
                if tokens_list and idx < len(tokens_list):
                    token_id = tokens_list[idx]

            if not token_id:
                logger.error(f"❌ No se encontró token para {direction}")
                self.notifier.send(f"❌ No se encontró token para {direction} en {question}")
                return

            # Configurar cliente con proxy wallet
            client = ClobClient(
                host="https://clob.polymarket.com",
                key=private_key,
                chain_id=137,
                signature_type=1,  # EOA firma por proxy
                funder=proxy_wallet if proxy_wallet else None
            )

            # Crear y enviar orden
            order_args = {
                "token_id": token_id,
                "price": round(price, 2),
                "size": bet,
                "side": "BUY"
            }

            logger.info(f"📤 Enviando orden: {order_args}")
            signed_order = client.create_order(order_args)
            response = client.post_order(signed_order)

            order_id = response.get("orderID") or response.get("id", "N/A")
            emoji = '🟢' if direction == 'Up' else '🔴'
            msg = (
                f"🟢 [REAL] Apuesta ejecutada\n"
                f"{emoji} Bitcoin 5Min: {direction}\n"
                f"💵 ${bet} USDC @ {price}\n"
                f"👥 Consenso: {signal['consensus_count']} wallets\n"
                f"🔗 Order ID: {order_id}"
            )
            logger.info(msg)
            self.notifier.send(msg)

        except Exception as e:
            error_msg = f"❌ Error ejecutando apuesta: {e}"
            logger.error(error_msg)
            self.notifier.send(error_msg)
