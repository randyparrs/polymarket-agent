import logging
import time
from typing import Dict, List
from polymarket_api import PolymarketAPI
from telegram_bot import TelegramNotifier

logger = logging.getLogger(__name__)

class PolymarketAgent:
    def __init__(self, config: dict):
        self.config = config
        self.api = PolymarketAPI()
        self.notifier = TelegramNotifier(
            config.get("telegram_token"),
            config.get("telegram_chat_id")
        )
        self.cycle_count = 0
        # Wallet a copiar
        self.target_wallet = config.get("target_wallet", "0x751a2b86cab503496efd325c8344e10159349ea1")
        # Trades ya vistos para no repetir
        self.seen_trades = set()

    def run_cycle(self):
        self.cycle_count += 1
        logger.info(f"🔄 Ciclo #{self.cycle_count} iniciado")
        logger.info(f"👁️ Monitoreando wallet: {self.target_wallet[:12]}...")

        # Obtener trades recientes de la wallet objetivo
        trades = self.api.get_wallet_trades(self.target_wallet, limit=20)

        if not trades:
            logger.info("😴 Sin trades recientes")
            return

        new_trades = []
        for trade in trades:
            trade_id = trade.get("transactionHash") or trade.get("id") or str(trade)
            if trade_id not in self.seen_trades:
                self.seen_trades.add(trade_id)
                # Solo procesar trades de las últimas 2 horas
                import time as _time
                ts = trade.get("timestamp", 0)
                if isinstance(ts, str):
                    try:
                        from datetime import datetime, timezone
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        ts = int(dt.timestamp())
                    except Exception:
                        ts = 0
                if ts and (_time.time() - ts) > 7200:
                    continue
                new_trades.append(trade)

        if not new_trades:
            logger.info("😴 Sin trades nuevos esta ronda")
            return

        logger.info(f"🆕 {len(new_trades)} trades nuevos detectados")

        for trade in new_trades:
            self._copy_trade(trade)

    def _copy_trade(self, trade: Dict):
        try:
            title = trade.get("title", "Mercado desconocido")
            outcome = trade.get("outcome", "")
            size = float(trade.get("size", 0) or 0)
            price = float(trade.get("price", 0) or 0)
            condition_id = trade.get("conditionId", "")
            asset = trade.get("asset", "")

            logger.info(f"📋 Trade detectado: {title} → {outcome} @ {price}")

            if not asset or price <= 0:
                logger.warning("⚠️ Trade sin datos suficientes, saltando")
                return

            bet = self.config["max_bet_usdc"]

            if self.config["simulation_mode"]:
                msg = (
                    f"🟡 [SIMULACIÓN] Copy Trade\n"
                    f"📋 {title}\n"
                    f"{'🟢' if 'up' in outcome.lower() or 'yes' in outcome.lower() else '🔴'} {outcome}\n"
                    f"💰 Precio: {price}\n"
                    f"💵 Apuesta simulada: ${bet} USDC"
                )
                logger.info(msg)
                self.notifier.send(msg)
                return

            # Ejecutar apuesta real
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import OrderArgs, ApiCreds

            private_key = self.config["private_key"]
            proxy_wallet = self.config.get("proxy_wallet", "")

            client = ClobClient(
                host="https://clob.polymarket.com",
                key=private_key,
                chain_id=137,
                signature_type=2,
                funder=proxy_wallet if proxy_wallet else None
            )

            api_key = self.config.get("polymarket_api_key")
            api_secret = self.config.get("polymarket_api_secret")
            api_passphrase = self.config.get("polymarket_api_passphrase")

            if api_key and api_secret and api_passphrase:
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
                logger.info(f"   POLYMARKET_API_KEY={creds.api_key}")
                logger.info(f"   POLYMARKET_API_SECRET={creds.api_secret}")
                logger.info(f"   POLYMARKET_API_PASSPHRASE={creds.api_passphrase}")

            token_id = str(asset).strip('"')

            order_args = OrderArgs(
                token_id=token_id,
                price=round(price, 2),
                size=round(bet, 2),
                side="BUY",
                fee_rate_bps=1000
            )

            logger.info(f"📤 Copiando trade: {outcome} @ {price} size={bet}")
            signed_order = client.create_order(order_args)
            response = client.post_order(signed_order)

            order_id = response.get("orderID") or response.get("id", "N/A")
            msg = (
                f"✅ [REAL] Copy Trade ejecutado\n"
                f"📋 {title}\n"
                f"{'🟢' if 'up' in outcome.lower() or 'yes' in outcome.lower() else '🔴'} {outcome}\n"
                f"💰 Precio: {price}\n"
                f"💵 ${bet} USDC\n"
                f"🔗 Order ID: {order_id}"
            )
            logger.info(msg)
            self.notifier.send(msg)

        except Exception as e:
            error_msg = f"❌ Error copiando trade: {e}"
            logger.error(error_msg)
            self.notifier.send(error_msg)

