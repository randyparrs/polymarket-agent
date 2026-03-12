import requests
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

POLYMARKET_API  = "https://gamma-api.polymarket.com"
DATA_API        = "https://data-api.polymarket.com"
CLOB_API        = "https://clob.polymarket.com"

# Keywords para detectar mercados de BTC
BTC_KEYWORDS = [
    "bitcoin", "btc", "bitcoin price", "btc price",
    "bitcoin above", "bitcoin below", "btc above", "btc below",
    "bitcoin hit", "btc hit", "bitcoin reach", "btc reach",
    "bitcoin end", "btc end", "satoshi"
]

class PolymarketAPI:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "polymarket-agent/1.0"})

    def get_btc_markets(self, limit: int = 30) -> List[Dict]:
        """Obtener solo mercados activos relacionados con BTC"""
        try:
            response = self.session.get(
                f"{POLYMARKET_API}/markets",
                params={
                    "active": True,
                    "closed": False,
                    "limit": limit,
                    "order": "volume24hr",
                    "ascending": False
                },
                timeout=10
            )
            response.raise_for_status()
            all_markets = response.json()

            # Filtrar solo mercados de BTC
            btc_markets = []
            for market in all_markets:
                question = market.get("question", "").lower()
                tags = [t.lower() for t in market.get("tags", [])]
                
                is_btc = any(kw in question for kw in BTC_KEYWORDS)
                is_btc = is_btc or any(kw in " ".join(tags) for kw in ["bitcoin", "btc"])
                
                if is_btc:
                    btc_markets.append(market)

            logger.info(f"🔶 {len(btc_markets)} mercados BTC activos encontrados")
            return btc_markets

        except Exception as e:
            logger.error(f"Error obteniendo mercados BTC: {e}")
            return []

    def get_markets(self, limit: int = 50) -> List[Dict]:
        """Obtener mercados activos generales"""
        try:
            response = self.session.get(
                f"{POLYMARKET_API}/markets",
                params={"active": True, "closed": False, "limit": limit,
                        "order": "volume24hr", "ascending": False},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error obteniendo mercados: {e}")
            return []

    def get_market_trades(self, market_id: str, limit: int = 100) -> List[Dict]:
        """Obtener trades recientes de un mercado"""
        try:
            response = self.session.get(
                f"{CLOB_API}/trades",
                params={"market": market_id, "limit": limit},
                timeout=10
            )
            response.raise_for_status()
            return response.json().get("data", [])
        except Exception as e:
            logger.error(f"Error obteniendo trades del mercado {market_id}: {e}")
            return []

    def get_wallet_trades(self, wallet_address: str, limit: int = 200) -> List[Dict]:
        """Obtener historial de trades de una wallet"""
        try:
            response = self.session.get(
                f"{CLOB_API}/trades",
                params={"maker_address": wallet_address.lower(), "limit": limit},
                timeout=10
            )
            response.raise_for_status()
            return response.json().get("data", [])
        except Exception as e:
            logger.error(f"Error obteniendo trades de wallet {wallet_address}: {e}")
            return []

    def get_wallet_btc_trades(self, wallet_address: str, limit: int = 200) -> List[Dict]:
        """Obtener solo trades de BTC de una wallet"""
        all_trades = self.get_wallet_trades(wallet_address, limit)
        btc_trades = []
        
        for trade in all_trades:
            market_id = trade.get("market", "")
            # Buscar en el título/outcome si es BTC
            outcome = trade.get("outcome", "").lower()
            title = trade.get("title", "").lower()
            
            is_btc = (
                any(kw in title for kw in BTC_KEYWORDS) or
                any(kw in outcome for kw in ["bitcoin", "btc"])
            )
            
            if is_btc:
                btc_trades.append(trade)
        
        return btc_trades

    def get_top_traders(self, limit: int = 60) -> List[Dict]:
        """Obtener top traders del leaderboard"""
        try:
            response = self.session.get(
                f"{DATA_API}/v1/leaderboard",
                params={"limit": limit},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            # La API devuelve lista directa o dict con key "data"
            if isinstance(data, list):
                return data
            return data.get("data", data)
        except Exception as e:
            logger.error(f"Error obteniendo leaderboard: {e}")
            return []

    def get_market_by_id(self, market_id: str) -> Dict:
        """Obtener detalles de un mercado"""
        try:
            response = self.session.get(
                f"{POLYMARKET_API}/markets/{market_id}",
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error obteniendo mercado {market_id}: {e}")
            return {}
