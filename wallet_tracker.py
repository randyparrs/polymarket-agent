import logging
from typing import List, Dict
from collections import defaultdict
from polymarket_api import PolymarketAPI

logger = logging.getLogger(__name__)

TOP_WALLETS_TARGET = 15

class WalletTracker:
    def __init__(self, api: PolymarketAPI):
        self.api = api

    def get_top_wallets(self, count: int = TOP_WALLETS_TARGET) -> List[str]:
        """Obtener top wallets del leaderboard"""
        traders = self.api.get_top_traders(limit=count * 2)

        if not traders:
            logger.warning("⚠️ No se pudo obtener leaderboard")
            return []

        wallets = []
        for trader in traders:
            address = (
                trader.get("proxyWallet") or
                trader.get("proxy_wallet") or
                trader.get("address") or
                trader.get("user")
            )
            if address and len(str(address)) > 10:
                wallets.append(str(address))
            if len(wallets) >= count:
                break

        logger.info(f"✅ {len(wallets)} top wallets obtenidas del leaderboard")
        return wallets

    def get_btc5min_signal(self, wallets: List[str], market_condition_id: str, min_consensus: int = 3) -> Dict:
        """
        Analizar qué están apostando las top wallets en mercados BTC 5min recientes.
        Busca en los ultimos 50 trades de cada wallet cualquier mercado btc-updown-5m.
        """
        votes = {"Up": [], "Down": []}

        for wallet in wallets:
            trades = self.api.get_wallet_trades(wallet, limit=100)

            for trade in trades:
                try:
                    outcome = str(trade.get("outcome", "") or "").strip()
                    title = str(trade.get("title", "") or "").lower()
                    slug = str(trade.get("slug", "") or "").lower()
                    event_slug = str(trade.get("eventSlug", "") or "").lower()
                    price = float(trade.get("price", 0) or 0)

                    # Verificar que es un mercado BTC 5min (cualquiera, no solo el actual)
                    is_btc5 = (
                        "btc-updown-5m" in slug or
                        "btc-updown-5m" in event_slug or
                        ("bitcoin" in title and ("up or down" in title) and ("5" in title or "min" in title))
                    )

                    if not is_btc5 or price <= 0:
                        continue

                    outcome_lower = outcome.lower()
                    if "up" in outcome_lower and wallet not in votes["Up"] and wallet not in votes["Down"]:
                        votes["Up"].append(wallet)
                        break  # un voto por wallet
                    elif "down" in outcome_lower and wallet not in votes["Up"] and wallet not in votes["Down"]:
                        votes["Down"].append(wallet)
                        break  # un voto por wallet

                except Exception:
                    continue

        up_count = len(votes["Up"])
        down_count = len(votes["Down"])
        total = up_count + down_count

        logger.info(f"📊 Votos — Up: {up_count} | Down: {down_count} | Total: {total} wallets")

        if total == 0:
            return {}

        # Determinar dirección ganadora
        if up_count > down_count and up_count >= min_consensus:
            direction = "Up"
            consensus = up_count
        elif down_count > up_count and down_count >= min_consensus:
            direction = "Down"
            consensus = down_count
        else:
            logger.info("😴 Sin consenso suficiente esta ronda.")
            return {}

        confidence = consensus / len(wallets) * 100

        logger.info(f"🎯 Señal: {direction} | Consenso: {consensus}/{len(wallets)} ({confidence:.1f}%)")

        return {
            "direction": direction,
            "consensus_count": consensus,
            "confidence_pct": confidence,
            "up_votes": up_count,
            "down_votes": down_count,
            "total_voters": total
        }

