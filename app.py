from __future__ import annotations

import flet as ft

from config import DEFAULT_ZOOM_LEVEL
from handlers import bind_handlers
from state import AppState
from tasks import clock_loop, nowcast_loop, temp_loop
from ui import build_controls, build_layout
from ui_types import AppContext
from weather_service import render_nowcast


async def main(page: ft.Page):
    page.title = "勤怠管理"
    page.padding = 24
    page.scroll = "hidden"

    try:
        page.window.full_screen = True
    except Exception:
        pass

    state = AppState(zoom_level=DEFAULT_ZOOM_LEVEL)
    ui = build_controls(page, state)
    ctx = AppContext(page=page, state=state, ui=ui)

    bind_handlers(ctx)
    page.add(build_layout(ctx))

    def _on_resized(_e) -> None:
        try:
            page.run_task(render_nowcast, ctx, False)
        except Exception:
            pass

    try:
        page.on_resized = _on_resized
    except Exception:
        pass

    page.run_task(clock_loop, ctx)
    page.run_task(temp_loop, ctx)
    page.run_task(nowcast_loop, ctx)


if __name__ == "__main__":
    ft.run(main)
