import logging
from typing import List, Dict
from collections import defaultdict
from polymarket_api import PolymarketAPI

logger = logging.getLogger(__name__)

class WalletTracker:
    def __init__(self, api: PolymarketAPI):
        self.api = api

    def get_top_wallets(self, count: int = 10) -> List[str]:
        """Obtener las top wallets por rendimiento"""
        traders = self.api.get_top_traders(limit=count * 2)
        
        if not traders:
            logger.warning("No se pudo obtener leaderboard, usando wallets conocidas de respaldo")
            return self._fallback_wallets()[:count]

        wallets = []
        for trader in traders:
            address = trader.get("proxy_wallet") or trader.get("address")
            if address:
                wallets.append(address)
            if len(wallets) >= count:
                break

        logger.info(f"Top {len(wallets)} wallets obtenidas del leaderboard")
        return wallets

    def get_consensus_signals(self, wallets: List[str], min_consensus: int = 4) -> List[Dict]:
        """
        Analiza qué están apostando las top wallets.
        Retorna señales donde al menos min_consensus wallets coinciden.
        """
        # Agrupar apuestas recientes por mercado+outcome
        market_votes = defaultdict(lambda: {
            "wallets": [],
            "prices": [],
            "token_id": None,
            "outcome": None,
            "question": None,
            "market_id": None
        })

        for wallet in wallets:
            trades = self.api.get_wallet_trades(wallet, limit=50)
            
            for trade in trades:
                try:
                    market_id = trade.get("market")
                    outcome = trade.get("outcome")
                    price = float(trade.get("price", 0))
                    token_id = trade.get("asset_id")
                    
                    if not market_id or not outcome or price <= 0:
                        continue

                    # Solo considerar apuestas con precio razonable (5%-95%)
                    if price < 0.05 or price > 0.95:
                        continue

                    key = f"{market_id}_{outcome}"
                    
                    if wallet not in market_votes[key]["wallets"]:
                        market_votes[key]["wallets"].append(wallet)
                        market_votes[key]["prices"].append(price)
                        market_votes[key]["token_id"] = token_id
                        market_votes[key]["outcome"] = outcome
                        market_votes[key]["market_id"] = market_id
                        
                        # Obtener pregunta del mercado si no la tenemos
                        if not market_votes[key]["question"]:
                            market_data = self.api.get_market_by_id(market_id)
                            market_votes[key]["question"] = market_data.get("question", "Mercado desconocido")

                except Exception as e:
                    logger.debug(f"Error procesando trade: {e}")
                    continue

        # Filtrar por consenso mínimo
        signals = []
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
                    "wallets": data["wallets"]
                })

        # Ordenar por consenso (mayor primero)
        signals.sort(key=lambda x: x["consensus_count"], reverse=True)
        
        logger.info(f"Señales con consenso >= {min_consensus}: {len(signals)}")
        return signals

    def _fallback_wallets(self) -> List[str]:
        """Wallets conocidas de alto rendimiento como respaldo"""
        return [
            "0x1234567890abcdef1234567890abcdef12345678",  # Placeholder
        ]
