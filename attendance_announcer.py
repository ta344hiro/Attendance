from __future__ import annotations

import asyncio

from voice import speak_jp
from weather_service import will_rain_within_1h_by_nowcast


def announce_touch_card() -> None:
    speak_jp("カードをタッチしてください。")


def announce_processing() -> None:
    speak_jp("処理中です。")


def announce_done(action: str, hour: int | None = None, minute: int | None = None) -> None:
    text = "記録を完了しました。"

    if action == "IN":
        text += "今日も一日頑張りましょう。"
        speak_jp(text)
        return

    text += "今日も一日お疲れ様でした。"

    try:
        will_rain, first_dt = will_rain_within_1h_by_nowcast()
        if will_rain:
            text += "この先、雨のため傘を忘れずお持ちください。"
    except Exception:
        pass

    speak_jp(text)


async def run_announce(fn, *args) -> None:
    await asyncio.to_thread(fn, *args)