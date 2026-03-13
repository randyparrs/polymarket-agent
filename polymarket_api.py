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
        """Obtener el mercado BTC 5min mas cercano al tiempo actual"""
        from datetime import datetime, timezone
        import re as _re

        now_ts = int(datetime.now(timezone.utc).timestamp())

        try:
            response = self.session.get(
                f"{POLYMARKET_API}/events",
                params={"active": True, "closed": False, "limit": 200, "order": "startDate", "ascending": False},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                events = data if isinstance(data, list) else data.get("data", [])

                # Log todos los slugs btc para ver qué hay
                btc_events = [e for e in events if "btc-updown-5m" in str(e.get("slug","")).lower()]
                logger.info(f"🔎 Eventos btc-updown-5m encontrados: {len(btc_events)}")
                for e in btc_events[:5]:
                    logger.info(f"  → {e.get('slug')} | startDate:{e.get('startDate')} | endDate:{e.get('endDate')}")

                # Buscar el mercado con startDate mas reciente que ya haya comenzado
                # o el que esta a punto de comenzar (proximo)
                started = []
                upcoming = []

                for event in events:
                    slug = str(event.get("slug", "") or "").lower()
                    if "btc-updown-5m" not in slug:
                        continue
                    start_str = event.get("startDate", "") or ""
                    try:
                        from datetime import datetime, timezone
                        start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                        start_ts = int(start_dt.timestamp())
                        markets = event.get("markets", [])
                        if not markets:
                            continue
                        if start_ts <= now_ts:
                            started.append((start_ts, event))
                        else:
                            upcoming.append((start_ts, event))
                    except Exception:
                        continue

                # Preferir el mas reciente que ya empezo
                if started:
                    started.sort(key=lambda x: x[0], reverse=True)
                    best_event = started[0][1]
                    logger.info(f"✅ BTC 5min EN CURSO: {best_event.get('title')}")
                    return best_event.get("markets", [])[0]

                # Si no hay ninguno activo, usar el proximo
                if upcoming:
                    upcoming.sort(key=lambda x: x[0])
                    best_event = upcoming[0][1]
                    secs = upcoming[0][0] - now_ts
                    logger.info(f"⏳ BTC 5min PROXIMO en {secs}s: {best_event.get('title')}")
                    return best_event.get("markets", [])[0]

        except Exception as e:
            logger.error(f"Error buscando BTC 5min: {e}")

        logger.warning("⚠️ No se encontro mercado BTC 5min activo")
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

    def get_active_traders_in_market(self, condition_id: str, limit: int = 100) -> list:
        """Obtener wallets que han apostado en este mercado especifico"""
        try:
            response = self.session.get(
                f"{DATA_API}/trades",
                params={"conditionId": condition_id, "limit": limit},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            trades = data if isinstance(data, list) else data.get("data", [])

            wallets = []
            seen = set()
            for trade in trades:
                wallet = trade.get("proxyWallet") or trade.get("user")
                if wallet and wallet not in seen:
                    seen.add(wallet)
                    wallets.append(wallet)

            logger.info(f"👥 Traders en mercado {condition_id[:10]}...: {len(wallets)}")
            return wallets
        except Exception as e:
            logger.debug(f"Error obteniendo traders del mercado: {e}")
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
