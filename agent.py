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

        market = self.api.get_current_btc5min_market()

        if not market:
            logger.warning("⚠️ No se encontró mercado BTC 5min activo. Reintentando...")
            return

        condition_id = market.get("conditionId") or market.get("condition_id") or market.get("id")
        question = market.get("question", "Bitcoin Up or Down - 5 Minutes")

        logger.info(f"🔶 Mercado activo: {question}")
        logger.info(f"   ID: {condition_id}")

        if condition_id == self.last_market_id:
            logger.info("⏭️ Mismo mercado que el ciclo anterior, esperando el siguiente...")
            return

        top_wallets = self.tracker.get_top_wallets(self.config["top_wallets_count"])
        if not top_wallets:
            logger.warning("⚠️ No se pudieron obtener wallets.")
            return

        active_traders = self.api.get_active_traders_in_market(condition_id, limit=100)
        if active_traders:
            logger.info(f"👥 {len(active_traders)} traders activos en este mercado")
            experts = self.tracker.get_btc5min_experts(active_traders, min_win_rate=0.55, min_trades=10)
            combined = list(dict.fromkeys(experts + top_wallets))[:50]
        else:
            combined = top_wallets

        signal = self.tracker.get_btc5min_signal(
            combined,
            condition_id,
            min_consensus=self.config["min_consensus"]
        )

        if not signal:
            return

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
            from py_clob_client.clob_types import OrderArgs

            direction = signal["direction"]
            bet = self.config["max_bet_usdc"]
            private_key = self.config["private_key"]
            proxy_wallet = self.config.get("proxy_wallet", "")

            # Buscar token_id correcto
            token_id = None
            price = 0.50

            # Opción 1: campo "tokens"
            tokens = market.get("tokens", [])
            for token in tokens:
                outcome = str(token.get("outcome", "") or "").lower()
                if direction.lower() in outcome:
                    token_id = str(token.get("token_id") or token.get("tokenId") or "").strip('"')
                    price = float(token.get("price", 0.50) or 0.50)
                    break

            # Opción 2: campo "clobTokenIds"
            if not token_id:
                clob_ids = market.get("clobTokenIds", [])
                if isinstance(clob_ids, list) and len(clob_ids) >= 2:
                    idx = 0 if direction == "Up" else 1
                    token_id = str(clob_ids[idx]).strip('"')

            # Opción 3: outcomes + clobTokenIds
            if not token_id:
                outcomes = market.get("outcomes", "[]")
                if isinstance(outcomes, str):
                    import json
                    try:
                        outcomes = json.loads(outcomes)
                    except Exception:
                        outcomes = []
                for i, o in enumerate(outcomes):
                    if direction.lower() in str(o).lower():
                        clob_ids = market.get("clobTokenIds", [])
                        if isinstance(clob_ids, str):
                            import json
                            try:
                                clob_ids = json.loads(clob_ids)
                            except Exception:
                                clob_ids = []
                        if i < len(clob_ids):
                            token_id = str(clob_ids[i]).strip('"')
                        break

            logger.info(f"🎯 Token ID encontrado: {token_id} | Precio: {price}")

            if not token_id or token_id in ['', '"', "'"]:
                logger.error(f"❌ No se encontró token válido para {direction}")
                self.notifier.send(f"❌ Token no encontrado para {direction}")
                return

            client = ClobClient(
                host="https://clob.polymarket.com",
                key=private_key,
                chain_id=137,
                signature_type=1,
                funder=proxy_wallet if proxy_wallet else None
            )

            api_key = self.config.get("polymarket_api_key")
            api_secret = self.config.get("polymarket_api_secret")
            api_passphrase = self.config.get("polymarket_api_passphrase")

            if api_key and api_secret and api_passphrase:
                from py_clob_client.clob_types import ApiCreds
                creds = ApiCreds(
                    api_key=api_key,
                    api_secret=api_secret,
                    api_passphrase=api_passphrase
                )
                client.set_api_creds(creds)
            else:
                logger.info("🔑 Generando API credentials...")
                creds = client.create_or_derive_api_creds()
                client.set_api_creds(creds)
                logger.info(f"✅ API Key generada: {creds.api_key[:10]}...")
                logger.info(f"💾 Guarda estas credenciales:")
                logger.info(f"   POLYMARKET_API_KEY={creds.api_key}")
                logger.info(f"   POLYMARKET_API_SECRET={creds.api_secret}")
                logger.info(f"   POLYMARKET_API_PASSPHRASE={creds.api_passphrase}")

            order_args = OrderArgs(
                token_id=token_id,
                price=round(price, 2),
                size=round(bet, 2),
                side="BUY"
            )

            logger.info(f"📤 Enviando orden: token={token_id[:10]}... price={price} size={bet} fee={fee_rate}")
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
