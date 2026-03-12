import requests
import logging

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.enabled = bool(token and chat_id)

    def send(self, message: str) -> bool:
        if not self.enabled:
            logger.info(f"[Telegram desactivado] {message}")
            return False

        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            response = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML"
            }, timeout=10)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Error enviando mensaje Telegram: {e}")
            return False
