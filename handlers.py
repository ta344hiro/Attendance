from __future__ import annotations

import asyncio

from attendance_service import wait_and_record
from card_reader import read_recent_logs
from config import ZOOM_MAX, ZOOM_MIN
from ui import build_logs_dialog, refresh_zoom_ui
from ui_types import AppContext
from weather_service import render_nowcast


def bind_handlers(ctx: AppContext) -> None:
    async def on_checkin(_e) -> None:
        if ctx.state.busy:
            return
        ctx.page.run_task(wait_and_record, ctx, "IN")

    async def on_checkout(_e) -> None:
        if ctx.state.busy:
            return
        ctx.page.run_task(wait_and_record, ctx, "OUT")

    async def on_cancel(_e) -> None:
        if not ctx.state.busy:
            return
        ctx.state.cancel_event.set()

    async def on_show_logs(_e) -> None:
        entries = await asyncio.to_thread(read_recent_logs, 50)
        dialog = build_logs_dialog(entries)

        def close_dialog(_evt) -> None:
            ctx.page.pop_dialog()
            ctx.page.update()

        if dialog.actions:
            dialog.actions[0].on_click = close_dialog

        ctx.page.show_dialog(dialog)
        ctx.page.update()

    async def set_zoom(new_lv: int) -> None:
        bounded = max(ZOOM_MIN, min(ZOOM_MAX, new_lv))
        if bounded == ctx.state.zoom_level:
            refresh_zoom_ui(ctx)
            return

        ctx.state.zoom_level = bounded
        refresh_zoom_ui(ctx)

        try:
            await render_nowcast(ctx, refresh_frame=False)
        except Exception:
            pass

    async def on_zoom_minus(_e) -> None:
        await set_zoom(ctx.state.zoom_level - 1)

    async def on_zoom_plus(_e) -> None:
        await set_zoom(ctx.state.zoom_level + 1)

    async def on_zoom_change_end(e) -> None:
        try:
            new_lv = int(round(float(e.control.value)))
        except Exception:
            return
        await set_zoom(new_lv)

    ctx.ui.checkin_btn.on_click = on_checkin
    ctx.ui.checkout_btn.on_click = on_checkout
    ctx.ui.cancel_btn.on_click = on_cancel
    ctx.ui.log_btn.on_click = on_show_logs

    ctx.ui.btn_minus.on_click = on_zoom_minus
    ctx.ui.btn_plus.on_click = on_zoom_plus

    try:
        ctx.ui.zoom_slider.on_change_end = on_zoom_change_end
    except Exception:
        ctx.ui.zoom_slider.on_change = on_zoom_change_end