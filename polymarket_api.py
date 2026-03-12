import requests
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

POLYMARKET_API  = "https://gamma-api.polymarket.com"
DATA_API        = "https://data-api.polymarket.com"

# Slugs exactos del mercado Bitcoin Up or Down 5 min
BTC_5MIN_SLUGS = [
    "bitcoin-up-or-down-5-minutes",
    "btc-up-or-down-5-minutes",
    "bitcoin-up-or-down",
]

class PolymarketAPI:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "polymarket-agent/1.0"})
        self._trades_logged = False

    def get_current_btc5min_market(self) -> Dict:
        """Obtener el mercado activo actual de Bitcoin Up or Down 5 Min"""
        # Buscar por slug conocido
        for slug in BTC_5MIN_SLUGS:
            try:
                response = self.session.get(
                    f"{POLYMARKET_API}/markets",
                    params={"slug": slug, "active": True, "closed": False},
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    markets = data if isinstance(data, list) else data.get("data", [])
                    if markets:
                        logger.info(f"✅ Mercado BTC 5min encontrado: {markets[0].get('question', slug)}")
                        return markets[0]
            except Exception:
                continue

        # Búsqueda por keyword si slug no funciona
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
            markets = data if isinstance(data, list) else data.get("data", [])

            for market in markets:
                question = str(market.get("question", "") or "").lower()
                slug = str(market.get("slug", "") or "").lower()
                if ("bitcoin" in question or "btc" in question) and ("5 min" in question or "5min" in slug):
                    logger.info(f"✅ Mercado BTC 5min encontrado: {market.get('question')}")
                    return market

        except Exception as e:
            logger.error(f"Error buscando mercado BTC 5min: {e}")

        return {}

    def get_recent_trades_for_market(self, condition_id: str, limit: int = 100) -> List[Dict]:
        """Obtener trades recientes de un mercado específico"""
        try:
            response = self.session.get(
                f"{DATA_API}/trades",
                params={"conditionId": condition_id, "limit": limit},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            result = data if isinstance(data, list) else data.get("data", [])
            if result and not self._trades_logged:
                logger.info(f"🔎 Campos de trades: {list(result[0].keys())}")
                self._trades_logged = True
            return result
        except Exception as e:
            logger.error(f"Error obteniendo trades del mercado: {e}")
            return []

    def get_top_traders(self, limit: int = 60) -> List[Dict]:
        """Obtener top traders del leaderboard"""
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
        return []

    def get_wallet_trades(self, wallet_address: str, limit: int = 50) -> List[Dict]:
        """Obtener trades recientes de una wallet"""
        try:
            response = self.session.get(
                f"{DATA_API}/trades",
                params={"user": wallet_address.lower(), "limit": limit},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else data.get("data", [])
        except Exception as e:
            logger.debug(f"Error trades wallet {wallet_address[:10]}: {e}")
            return []

