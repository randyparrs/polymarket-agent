import logging
from typing import List, Dict
from collections import defaultdict
from polymarket_api import PolymarketAPI

logger = logging.getLogger(__name__)

# ── Filtros de calidad ──────────────────────────────────────────
MIN_TOTAL_TRADES    = 30     # Mínimo trades totales (actividad general)
MIN_BTC_TRADES      = 5      # Mínimo trades en mercados BTC
MIN_ROI_PERCENT     = 40     # ROI mínimo sobre trades BTC (%)
MIN_WIN_RATE        = 0.55   # Win rate mínimo en BTC (55%)
TOP_WALLETS_TARGET  = 15     # Cuántas wallets queremos al final
# ───────────────────────────────────────────────────────────────

class WalletTracker:
    def __init__(self, api: PolymarketAPI):
        self.api = api

    def get_top_wallets(self, count: int = TOP_WALLETS_TARGET) -> List[str]:
        """
        Obtener las mejores wallets rankeadas por:
        1. ROI en mercados BTC
        2. Actividad (número de trades BTC)
        3. Win rate en BTC
        """
        logger.info("🔍 Buscando top wallets especializadas en BTC...")

        traders = self.api.get_top_traders(limit=count * 4)

        if not traders:
            logger.warning("⚠️ No se pudo obtener leaderboard")
            return []

        scored_wallets = []

        for trader in traders:
            address = trader.get("proxy_wallet") or trader.get("address")
            if not address:
                continue

            stats = self._analyze_btc_wallet(address)

            if not self._passes_filter(stats, address):
                continue

            # Score combinado: ROI (60%) + Actividad (20%) + Win rate (20%)
            score = (
                stats["roi"] * 0.6 +
                min(stats["btc_trades"], 100) * 0.2 +   # cap a 100 para no sesgar
                stats["win_rate"] * 100 * 0.2
            )

            scored_wallets.append({
                "address": address,
                "score": score,
                "roi": stats["roi"],
                "win_rate": stats["win_rate"],
                "btc_trades": stats["btc_trades"],
                "total_trades": stats["total_trades"]
            })

        # Ordenar por score descendente
        scored_wallets.sort(key=lambda x: x["score"], reverse=True)
        top = scored_wallets[:count]

        logger.info(f"🏆 Top {len(top)} wallets BTC seleccionadas:")
        for i, w in enumerate(top, 1):
            logger.info(
                f"  #{i} {w['address'][:10]}... | "
                f"ROI: {w['roi']:.1f}% | "
                f"Win: {w['win_rate']*100:.1f}% | "
                f"Trades BTC: {w['btc_trades']}"
            )

        return [w["address"] for w in top]

    def _analyze_btc_wallet(self, address: str) -> Dict:
        """Analizar rendimiento de una wallet específicamente en mercados BTC"""
        all_trades = self.api.get_wallet_trades(address, limit=200)

        if not all_trades:
            return self._empty_stats()

        total_trades = len(all_trades)

        # Filtrar solo trades de BTC cerrados
        btc_wins = 0
        btc_losses = 0
        total_invested = 0
        total_returned = 0

        for trade in all_trades:
            try:
                title = trade.get("title", "").lower()
                outcome = trade.get("outcome", "")
                price = float(trade.get("price", 0))
                size = float(trade.get("size", 0))

                # Verificar si es mercado BTC
                from polymarket_api import BTC_KEYWORDS
                is_btc = any(kw in title for kw in BTC_KEYWORDS)
                if not is_btc:
                    continue

                # Solo trades con resultado
                if outcome not in ["WIN", "LOSE", "yes", "no"]:
                    continue

                if price <= 0 or size <= 0:
                    continue

                cost = price * size
                total_invested += cost

                if outcome in ["WIN", "yes"]:
                    total_returned += size
                    btc_wins += 1
                else:
                    btc_losses += 1

            except Exception:
                continue

        btc_trades = btc_wins + btc_losses

        if btc_trades < MIN_BTC_TRADES:
            return {**self._empty_stats(), "total_trades": total_trades, "btc_trades": btc_trades}

        profit = total_returned - total_invested
        roi = (profit / total_invested * 100) if total_invested > 0 else 0
        win_rate = btc_wins / btc_trades if btc_trades > 0 else 0

        return {
            "roi": roi,
            "win_rate": win_rate,
            "btc_trades": btc_trades,
            "total_trades": total_trades,
            "profit": profit
        }

    def _passes_filter(self, stats: Dict, address: str) -> bool:
        """Verificar si una wallet pasa los filtros de calidad"""
        if stats["total_trades"] < MIN_TOTAL_TRADES:
            logger.debug(f"❌ {address[:10]}... actividad baja: {stats['total_trades']} trades")
            return False
        if stats["btc_trades"] < MIN_BTC_TRADES:
            logger.debug(f"❌ {address[:10]}... pocos trades BTC: {stats['btc_trades']}")
            return False
        if stats["roi"] < MIN_ROI_PERCENT:
            logger.debug(f"❌ {address[:10]}... ROI BTC bajo: {stats['roi']:.1f}%")
            return False
        if stats["win_rate"] < MIN_WIN_RATE:
            logger.debug(f"❌ {address[:10]}... win rate bajo: {stats['win_rate']*100:.1f}%")
            return False
        return True

    def _empty_stats(self) -> Dict:
        return {"roi": 0, "win_rate": 0, "btc_trades": 0, "total_trades": 0, "profit": 0}

    def get_consensus_signals(self, wallets: List[str], min_consensus: int = 5) -> List[Dict]:
        """
        Detectar señales de consenso SOLO en mercados BTC activos.
        Mínimo 5 de 15 wallets de acuerdo para generar señal.
        """
        # Obtener mercados BTC activos primero
        btc_markets = self.api.get_btc_markets(limit=30)
        btc_market_ids = {m.get("id") or m.get("condition_id") for m in btc_markets}

        logger.info(f"🔶 Monitoreando {len(btc_market_ids)} mercados BTC activos")

        market_votes = defaultdict(lambda: {
            "wallets": [], "prices": [], "token_id": None,
            "outcome": None, "question": None, "market_id": None
        })

        for wallet in wallets:
            trades = self.api.get_wallet_trades(wallet, limit=100)

            for trade in trades:
                try:
                    market_id = trade.get("market")
                    outcome = trade.get("outcome")
                    price = float(trade.get("price", 0))
                    token_id = trade.get("asset_id")
                    title = trade.get("title", "").lower()

                    if not market_id or not outcome or price <= 0:
                        continue

                    # Solo mercados BTC
                    from polymarket_api import BTC_KEYWORDS
                    is_btc_trade = (
                        market_id in btc_market_ids or
                        any(kw in title for kw in BTC_KEYWORDS)
                    )
                    if not is_btc_trade:
                        continue

                    # Precios razonables (5%–95%)
                    if price < 0.05 or price > 0.95:
                        continue

                    key = f"{market_id}_{outcome}"

                    if wallet not in market_votes[key]["wallets"]:
                        market_votes[key]["wallets"].append(wallet)
                        market_votes[key]["prices"].append(price)
                        market_votes[key]["token_id"] = token_id
                        market_votes[key]["outcome"] = outcome
                        market_votes[key]["market_id"] = market_id

                        if not market_votes[key]["question"]:
                            market_data = self.api.get_market_by_id(market_id)
                            market_votes[key]["question"] = market_data.get(
                                "question", "Mercado BTC desconocido"
                            )

                except Exception as e:
                    logger.debug(f"Error procesando trade: {e}")
                    continue

        # Filtrar por consenso mínimo
        signals = []
        total_wallets = len(wallets)

        for key, data in market_votes.items():
            consensus = len(data["wallets"])
            if consensus >= min_consensus and data["question"]:
                avg_price = sum(data["prices"]) / len(data["prices"])
                signals.append({
                    "market_id": data["market_id"],
                    "token_id": data["token_id"],
                    "question": data["question"],
                    "outcome": data["outcome"],
                    "avg_price": avg_price,
                    "consensus_count": consensus,
                    "consensus_pct": round(consensus / total_wallets * 100, 1),
                    "wallets": data["wallets"]
                })

        signals.sort(key=lambda x: x["consensus_count"], reverse=True)
        logger.info(f"🎯 Señales BTC con consenso >= {min_consensus}: {len(signals)}")
        return signals
