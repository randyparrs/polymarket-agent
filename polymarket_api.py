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

    def get_btc_markets(self, limit: int = 50) -> List[Dict]:
        """Obtener mercados activos relacionados con BTC"""
        btc_markets = []

        # Intentar búsqueda por tag/keyword en gamma API
        for search_term in ["bitcoin", "BTC", "Bitcoin"]:
            try:
                response = self.session.get(
                    f"{POLYMARKET_API}/markets",
                    params={
                        "active": True,
                        "closed": False,
                        "limit": limit,
                        "order": "volume24hr",
                        "ascending": False,
                        "tag": search_term
                    },
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    markets = data if isinstance(data, list) else data.get("data", data)
                    if markets:
                        btc_markets.extend(markets)
                        break
            except Exception:
                continue

        # Si no encontró por tag, traer todos y filtrar
        if not btc_markets:
            try:
                response = self.session.get(
                    f"{POLYMARKET_API}/markets",
                    params={
                        "active": True,
                        "closed": False,
                        "limit": 100,
                        "order": "volume24hr",
                        "ascending": False
                    },
                    timeout=10
                )
                response.raise_for_status()
                data = response.json()
                all_markets = data if isinstance(data, list) else data.get("data", [])

                for market in all_markets:
                    question = str(market.get("question", "") or "").lower()
                    title = str(market.get("title", "") or "").lower()
                    tags = market.get("tags", [])
                    tag_str = " ".join([str(t).lower() for t in (tags if isinstance(tags, list) else [])]) 

                    is_btc = (
                        any(kw in question for kw in BTC_KEYWORDS) or
                        any(kw in title for kw in BTC_KEYWORDS) or
                        any(kw in tag_str for kw in ["bitcoin", "btc"])
                    )
                    if is_btc:
                        btc_markets.append(market)

            except Exception as e:
                logger.error(f"Error obteniendo mercados: {e}")

        # Deduplicar
        seen = set()
        unique = []
        for m in btc_markets:
            mid = m.get("id") or m.get("condition_id") or m.get("market_slug")
            if mid and mid not in seen:
                seen.add(mid)
                unique.append(m)

        logger.info(f"🔶 {len(unique)} mercados BTC activos encontrados")
        return unique

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
        """Obtener historial de trades de una wallet usando Data API público"""
        try:
            response = self.session.get(
                f"{DATA_API}/trades",
                params={"user": wallet_address.lower(), "limit": limit},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            result = data if isinstance(data, list) else data.get("data", [])
            # Log estructura solo la primera vez
            if result and not hasattr(self, "_trades_logged"):
                logger.info(f"🔎 Campos de trades: {list(result[0].keys())}")
                self._trades_logged = True
            return result
        except Exception as e:
            logger.debug(f"Error trades wallet {wallet_address[:10]}: {e}")
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
        """Obtener top traders del leaderboard — ventana 30 días"""
        for window in ["30d", "7d", "all"]:
            try:
                response = self.session.get(
                    f"{DATA_API}/v1/leaderboard",
                    params={"limit": limit, "window": window},
                    timeout=10
                )
                response.raise_for_status()
                data = response.json()
                result = data if isinstance(data, list) else data.get("data", [])
                if result:
                    logger.info(f"✅ Leaderboard obtenido (window={window}): {len(result)} traders")
                    return result
            except Exception as e:
                logger.error(f"Error leaderboard window={window}: {e}")
                continue
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
