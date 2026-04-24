from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from config import JST, UPDATE_MIN
from ui import refresh_zoom_ui
from ui_types import AppContext
from weather_service import get_current_temp_amedas, render_nowcast

TEMP_UPDATE_MIN = UPDATE_MIN
NOWCAST_UPDATE_MIN = UPDATE_MIN


def next_tick(now: datetime, step_minutes: int) -> datetime:
    if step_minutes <= 0:
        raise ValueError("step_minutes must be >= 1")

    base = now.replace(second=0, microsecond=0)
    add = step_minutes - (base.minute % step_minutes)
    if add == 0:
        add = step_minutes
    return base + timedelta(minutes=add)


async def clock_loop(ctx: AppContext) -> None:
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]

    while True:
        now = datetime.now(JST)
        ctx.ui.time_info.value = f"{now.hour:02d}:{now.minute:02d}"
        ctx.ui.date_info.value = f"{now:%Y-%m-%d}({weekdays[now.weekday()]})"
        ctx.page.update()

        nxt = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        await asyncio.sleep((nxt - now).total_seconds())


async def temp_loop(ctx: AppContext) -> None:
    async def update_temp_once() -> None:
        try:
            temp, obs, _stname = await asyncio.to_thread(get_current_temp_amedas)
            ctx.ui.temp_info.value = f"{temp:.1f}度（{obs.hour:02d}:{obs.minute:02d} 観測）"
        except Exception:
            nxt = next_tick(datetime.now(JST), TEMP_UPDATE_MIN)
            ctx.ui.temp_info.value = f"取得失敗（次回 {nxt.hour:02d}:{nxt.minute:02d} 更新）"
        ctx.page.update()

    await update_temp_once()

    while True:
        now = datetime.now(JST)
        nxt = next_tick(now, TEMP_UPDATE_MIN)
        await asyncio.sleep((nxt - now).total_seconds())
        await update_temp_once()


async def nowcast_loop(ctx: AppContext) -> None:
    refresh_zoom_ui(ctx)
    await render_nowcast(ctx, refresh_frame=True)

    while True:
        now = datetime.now(JST)
        nxt = next_tick(now, NOWCAST_UPDATE_MIN)
        await asyncio.sleep((nxt - now).total_seconds())

        try:
            await render_nowcast(ctx, refresh_frame=True)
        except Exception:
            pass
