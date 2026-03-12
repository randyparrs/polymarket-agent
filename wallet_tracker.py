import logging
from typing import List, Dict
from collections import defaultdict
from polymarket_api import PolymarketAPI

logger = logging.getLogger(__name__)

# Filtros de calidad
MIN_TOTAL_TRADES    = 10
MIN_BTC_TRADES      = 2
MIN_ROI_PERCENT     = 10
MIN_WIN_RATE        = 0.50
TOP_WALLETS_TARGET  = 15

class WalletTracker:
    def __init__(self, api: PolymarketAPI):
        self.api = api

    def get_top_wallets(self, count: int = TOP_WALLETS_TARGET) -> List[str]:
        logger.info("🔍 Buscando top wallets especializadas en BTC...")
        traders = self.api.get_top_traders(limit=count * 4)

        if not traders:
            logger.warning("⚠️ No se pudo obtener leaderboard")
            return []

        # Log estructura para debugging
        if traders:
            logger.info(f"🔎 Campos del leaderboard: {list(traders[0].keys())}")
            logger.info(f"🔎 Ejemplo trader: {traders[0]}")

        scored_wallets = []

        for trader in traders:
            address = (
                trader.get("proxyWallet") or
                trader.get("proxy_wallet") or
                trader.get("address") or
                trader.get("user")
            )
            if not address or len(str(address)) < 10:
                continue

            stats = self._analyze_btc_wallet(str(address))

            if self._passes_filter(stats, str(address)):
                score = (
                    stats["roi"] * 0.6 +
                    min(stats["btc_trades"], 100) * 0.2 +
                    stats["win_rate"] * 100 * 0.2
                )
                scored_wallets.append({
                    "address": str(address),
                    "score": score,
                    **stats
                })

        if scored_wallets:
            scored_wallets.sort(key=lambda x: x["score"], reverse=True)
            top = scored_wallets[:count]
            logger.info(f"🏆 Top {len(top)} wallets BTC por ROI/actividad")
            for i, w in enumerate(top, 1):
                logger.info(f"  #{i} {w['address'][:10]}... ROI:{w['roi']:.1f}% Win:{w['win_rate']*100:.1f}% Trades:{w['btc_trades']}")
            return [w["address"] for w in top]

        # Fallback: usar top wallets del leaderboard sin filtro BTC
        logger.warning("⚠️ Sin historial BTC suficiente — usando top leaderboard directamente")
        fallback = []
        for trader in traders:
            address = (
                trader.get("proxyWallet") or
                trader.get("proxy_wallet") or
                trader.get("address") or
                trader.get("user")
            )
            if address and len(str(address)) > 10:
                fallback.append(str(address))
            if len(fallback) >= count:
                break

        logger.info(f"📋 Fallback: {len(fallback)} wallets del leaderboard")
        return fallback

    def _analyze_btc_wallet(self, address: str) -> Dict:
        all_trades = self.api.get_wallet_trades(address, limit=200)

        if not all_trades:
            return self._empty_stats()

        total_trades = len(all_trades)
        btc_wins = 0
        btc_losses = 0
        total_invested = 0
        total_returned = 0

        for trade in all_trades:
            try:
                title = str(trade.get("title", "") or trade.get("market", "")).lower()
                outcome = trade.get("outcome", "")
                price = float(trade.get("price", 0) or 0)
                size = float(trade.get("size", 0) or 0)

                from polymarket_api import BTC_KEYWORDS
                is_btc = any(kw in title for kw in BTC_KEYWORDS)
                if not is_btc:
                    continue

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
        if stats["total_trades"] < MIN_TOTAL_TRADES:
            return False
        if stats["btc_trades"] < MIN_BTC_TRADES:
            return False
        if stats["roi"] < MIN_ROI_PERCENT:
            return False
        if stats["win_rate"] < MIN_WIN_RATE:
            return False
        return True

    def _empty_stats(self) -> Dict:
        return {"roi": 0, "win_rate": 0, "btc_trades": 0, "total_trades": 0, "profit": 0}

    def get_consensus_signals(self, wallets: List[str], min_consensus: int = 3) -> List[Dict]:
        btc_markets = self.api.get_btc_markets(limit=30)
        btc_market_ids = {
            m.get("conditionId") or m.get("id") or m.get("condition_id")
            for m in btc_markets
            if m.get("conditionId") or m.get("id") or m.get("condition_id")
        }

        logger.info(f"🔶 Monitoreando {len(btc_market_ids)} mercados BTC activos")

        market_votes = defaultdict(lambda: {
            "wallets": [], "prices": [], "token_id": None,
            "outcome": None, "question": None, "market_id": None
        })

        btc_count = 0
        for wallet in wallets:
            trades = self.api.get_wallet_trades(wallet, limit=100)
            wallet_btc = 0

            for trade in trades:
                try:
                    market_id = trade.get("conditionId") or trade.get("market")
                    outcome = trade.get("outcome")
                    price = float(trade.get("price", 0) or 0)
                    token_id = trade.get("asset")
                    title = str(trade.get("title", "") or "").lower()

                    if not market_id or not outcome or price <= 0:
                        continue

                    from polymarket_api import BTC_KEYWORDS
                    is_btc = (
                        market_id in btc_market_ids or
                        any(kw in title for kw in BTC_KEYWORDS)
                    )
                    if not is_btc:
                        continue

                    if price < 0.05 or price > 0.95:
                        continue

                    key = f"{market_id}_{outcome}"
                    wallet_btc += 1

                    if wallet not in market_votes[key]["wallets"]:
                        market_votes[key]["wallets"].append(wallet)
                        market_votes[key]["prices"].append(price)
                        market_votes[key]["token_id"] = token_id
                        market_votes[key]["outcome"] = outcome
                        market_votes[key]["market_id"] = market_id

                        if not market_votes[key]["question"]:
                            market_votes[key]["question"] = str(trade.get("title", "") or market_id)

                except Exception as e:
                    logger.debug(f"Error procesando trade: {e}")
                    continue

            if wallet_btc > 0:
                logger.info(f"  🔍 {wallet[:10]}... → {wallet_btc} trades BTC encontrados")
                btc_count += wallet_btc

        logger.info(f"📊 Total trades BTC detectados: {btc_count} de {len(wallets)} wallets")

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
