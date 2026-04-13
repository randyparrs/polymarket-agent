import logging
from typing import List, Dict
from polymarket_api import PolymarketAPI

logger = logging.getLogger(__name__)

TOP_WALLETS_TARGET = 15

class WalletTracker:
    def __init__(self, api: PolymarketAPI):
        self.api = api
        self._btc5min_experts_cache = []

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

    def get_btc5min_experts(self, active_traders: List[str], min_win_rate: float = 0.55, min_trades: int = 3) -> List[str]:
        """
        Filtrar traders con mejor historial en BTC 5min.
        Analiza trades pasados y calcula win rate por wallet.
        """
        if self._btc5min_experts_cache:
            return self._btc5min_experts_cache

        wallet_stats = {}

        logger.info(f"🔍 Analizando historial de {len(active_traders)} traders en BTC 5min...")

        for wallet in active_traders:
            trades = self.api.get_wallet_trades(wallet, limit=200)
            wins = 0
            losses = 0

            for trade in trades:
                try:
                    slug = str(trade.get("slug", "") or "").lower()
                    event_slug = str(trade.get("eventSlug", "") or "").lower()
                    title = str(trade.get("title", "") or "").lower()

                    is_btc5 = (
                        "btc-updown-5m" in slug or
                        "btc-updown-5m" in event_slug or
                        ("bitcoin" in title and "up or down" in title)
                    )

                    if not is_btc5:
                        continue

                    # Verificar si fue ganadora
                    outcome = str(trade.get("outcome", "") or "").lower()
                    redeemed = trade.get("redeemed", False)
                    size = float(trade.get("size", 0) or 0)
                    price = float(trade.get("price", 0) or 0)

                    if redeemed and size > 0:
                        if price < 0.5:
                            wins += 1
                        else:
                            losses += 1
                    elif size > 0 and price > 0:
                        # Trade aún no resuelto, lo ignoramos
                        pass

                except Exception:
                    continue

            total = wins + losses
            if total >= min_trades:
                win_rate = wins / total
                wallet_stats[wallet] = {
                    "win_rate": win_rate,
                    "wins": wins,
                    "losses": losses,
                    "total": total
                }

        # Filtrar y ordenar por win rate
        experts = [
            w for w, s in wallet_stats.items()
            if s["win_rate"] >= min_win_rate
        ]
        experts.sort(key=lambda w: wallet_stats[w]["win_rate"], reverse=True)

        if experts:
            logger.info(f"⭐ {len(experts)} expertos BTC 5min encontrados (win rate >= {min_win_rate*100:.0f}%)")
            for w in experts[:5]:
                s = wallet_stats[w]
                logger.info(f"   {w[:10]}... W:{s['wins']} L:{s['losses']} ({s['win_rate']*100:.0f}%)")
        else:
            logger.info(f"⚠️ No se encontraron expertos con win rate >= {min_win_rate*100:.0f}%, usando todos")
            experts = active_traders

        self._btc5min_experts_cache = experts
        return experts

    def reset_cache(self):
        self._btc5min_experts_cache = []

    def get_btc5min_signal(self, wallets: List[str], market_condition_id: str, min_consensus: int = 2) -> Dict:
        """
        Analizar qué están apostando las wallets en el mercado BTC 5min actual.
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
                    cid = trade.get("conditionId", "")

                    is_btc5 = (
                        cid == market_condition_id or
                        "btc-updown-5m" in slug or
                        "btc-updown-5m" in event_slug or
                        ("bitcoin" in title and ("up or down" in title) and ("5" in title or "min" in title))
                    )

                    if not is_btc5 or price <= 0:
                        continue

                    outcome_lower = outcome.lower()
                    if "up" in outcome_lower and wallet not in votes["Up"] and wallet not in votes["Down"]:
                        votes["Up"].append(wallet)
                        break
                    elif "down" in outcome_lower and wallet not in votes["Up"] and wallet not in votes["Down"]:
                        votes["Down"].append(wallet)
                        break

                except Exception:
                    continue

        up_count = len(votes["Up"])
        down_count = len(votes["Down"])
        total = up_count + down_count

        logger.info(f"📊 Votos — Up: {up_count} | Down: {down_count} | Total: {total} wallets")

        if total == 0:
            return {}

        if up_count == down_count:
            logger.info("😴 Empate exacto — sin señal.")
            return {}
        elif up_count > down_count and up_count >= min_consensus:
            direction = "Up"
            consensus = up_count
        elif down_count > up_count and down_count >= min_consensus:
            direction = "Down"
            consensus = down_count
        else:
            logger.info("😴 Sin consenso suficiente esta ronda.")
            return {}

        confidence = consensus / max(len(wallets), 1) * 100
        logger.info(f"🎯 Señal: {direction} | Consenso: {consensus}/{len(wallets)} ({confidence:.1f}%)")

        return {
            "direction": direction,
            "consensus_count": consensus,
            "confidence_pct": confidence,
            "up_votes": up_count,
            "down_votes": down_count,
            "total_voters": total
        }
