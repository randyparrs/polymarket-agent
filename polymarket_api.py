import requests
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

POLYMARKET_API  = "https://gamma-api.polymarket.com"
DATA_API        = "https://data-api.polymarket.com"

# Slugs exactos del mercado Bitcoin Up or Down 5 min
BTC_5MIN_SLUGS = [
    "btc-updown-5m",
    "bitcoin-up-or-down-5-minutes",
    "btc-up-or-down-5-minutes",
]

BTC_5MIN_KEYWORDS = ["btc-updown-5m", "bitcoin up or down - 5", "btc up or down 5"]

class PolymarketAPI:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "polymarket-agent/1.0"})
        self._trades_logged = False

    def get_current_btc5min_market(self) -> Dict:
        """Obtener el mercado activo actual de Bitcoin Up or Down 5 Min"""

        # Buscar en el endpoint de events con slug base
        try:
            response = self.session.get(
                f"{POLYMARKET_API}/events",
                params={"active": True, "closed": False, "limit": 20, "slug": "btc-updown-5m"},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                events = data if isinstance(data, list) else data.get("data", [])
                logger.info(f"🔎 Events con slug btc-updown-5m: {len(events)}")
                for event in events:
                    markets = event.get("markets", [])
                    if markets:
                        logger.info(f"✅ Encontrado via events: {event.get('title', 'N/A')}")
                        return markets[0]
        except Exception as e:
            logger.debug(f"Error events slug: {e}")

        # Buscar todos los events recientes y filtrar
        try:
            response = self.session.get(
                f"{POLYMARKET_API}/events",
                params={"active": True, "closed": False, "limit": 50, "order": "startDate", "ascending": False},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                events = data if isinstance(data, list) else data.get("data", [])
                logger.info(f"🔎 Total events activos: {len(events)}")
                for event in events[:10]:
                    logger.info(f"  → {event.get('slug','')} | {event.get('title','')[:50]}")

                for event in events:
                    slug = str(event.get("slug", "") or "").lower()
                    title = str(event.get("title", "") or "").lower()
                    if "btc-updown" in slug or "btc-updown" in title or ("bitcoin" in title and "5" in title and ("up" in title or "down" in title)):
                        markets = event.get("markets", [])
                        if markets:
                            logger.info(f"✅ BTC 5min encontrado: {event.get('title')}")
                            return markets[0]
        except Exception as e:
            logger.error(f"Error buscando events BTC 5min: {e}")

        logger.warning("⚠️ No se encontró mercado BTC 5min activo")
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

           
      
