import requests
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

POLYMARKET_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

class PolymarketAPI:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "polymarket-agent/1.0"
        })

    def get_markets(self, limit: int = 50) -> List[Dict]:
        """Obtener mercados activos"""
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
            return response.json()
        except Exception as e:
            logger.error(f"Error obteniendo mercados: {e}")
            return []

    def get_market_trades(self, market_id: str, limit: int = 100) -> List[Dict]:
        """Obtener trades recientes de un mercado"""
        try:
            response = self.session.get(
                f"{CLOB_API}/trades",
                params={
                    "market": market_id,
                    "limit": limit
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except Exception as e:
            logger.error(f"Error obteniendo trades del mercado {market_id}: {e}")
            return []

    def get_wallet_trades(self, wallet_address: str, limit: int = 200) -> List[Dict]:
        """Obtener historial de trades de una wallet"""
        try:
            response = self.session.get(
                f"{CLOB_API}/trades",
                params={
                    "maker_address": wallet_address.lower(),
                    "limit": limit
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except Exception as e:
            logger.error(f"Error obteniendo trades de wallet {wallet_address}: {e}")
            return []

    def get_top_traders(self, limit: int = 20) -> List[Dict]:
        """Obtener top traders de Polymarket"""
        try:
            response = self.session.get(
                f"{POLYMARKET_API}/leaderboard",
                params={"limit": limit},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
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
