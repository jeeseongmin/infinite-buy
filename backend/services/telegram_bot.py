"""텔레그램 알림 봇"""

import logging

import httpx

from config import get_settings

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self):
        self.settings = get_settings()

    @property
    def _enabled(self) -> bool:
        return bool(self.settings.telegram_bot_token and self.settings.telegram_chat_id)

    async def send_message(self, text: str) -> bool:
        if not self._enabled:
            logger.info(f"[TELEGRAM-DISABLED] {text}")
            return False

        url = (
            f"https://api.telegram.org/bot{self.settings.telegram_bot_token}"
            f"/sendMessage"
        )
        payload = {
            "chat_id": self.settings.telegram_chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=10)
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"텔레그램 전송 실패: {e}")
            return False

    async def notify_buy(
        self,
        ticker: str,
        quantity: int,
        price: float,
        avg_cost: float,
        step: int,
        tranche_count: int,
    ):
        pnl_pct = ((price - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0
        text = (
            f"<b>BUY</b> {ticker}\n"
            f"{quantity}주 @ ${price:.2f}\n"
            f"avg ${avg_cost:.2f} ({pnl_pct:+.1f}%)\n"
            f"step {step}/{tranche_count}"
        )
        await self.send_message(text)

    async def notify_sell(
        self,
        ticker: str,
        quantity: int,
        price: float,
        pnl: float,
        pnl_pct: float,
    ):
        text = (
            f"<b>SELL ALL</b> {ticker}\n"
            f"{quantity}주 @ ${price:.2f}\n"
            f"PnL ${pnl:,.2f} ({pnl_pct*100:+.2f}%)"
        )
        await self.send_message(text)

    async def notify_state_change(self, ticker: str, from_state: str, to_state: str, reason: str):
        text = (
            f"<b>STATE</b> {ticker}\n"
            f"{from_state} → {to_state}\n"
            f"{reason}"
        )
        await self.send_message(text)

    async def notify_error(self, message: str):
        text = f"<b>ERROR</b>\n{message}"
        await self.send_message(text)


telegram_bot = TelegramBot()
