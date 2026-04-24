from __future__ import annotations

import asyncio
from datetime import datetime

from smartcard.Exceptions import CardConnectionException, NoCardException

from attendance_announcer import (
    announce_done,
    announce_processing,
    announce_touch_card,
    run_announce,
)
from card_reader import (
    NoReaderError,
    append_csv,
    get_uid,
    get_user_name,
    is_debounced,
    pick_reader,
)
from config import JST
from mattermost import send_attendance_message
from ui import (
    set_busy,
    set_status,
    view_done,
    view_error,
    view_idle,
    view_processing,
    view_waiting,
)
from ui_types import AppContext
from voice import speak_jp

READER_ERROR_MESSAGE = "カードリーダーが接続されていません。接続を確認してください。"


async def _speak_safe(fn, *args) -> None:
    try:
        await run_announce(fn, *args)
    except Exception:
        pass


async def _wait_for_reader_recovery(ctx: AppContext) -> None:
    while True:
        if ctx.state.cancel_event.is_set():
            return
        try:
            await asyncio.to_thread(pick_reader)
        except NoReaderError:
            await asyncio.sleep(1.0)
            continue
        else:
            set_status(ctx, view_waiting())
            return


async def _record_attendance(ctx: AppContext, action: str, card_id: str) -> None:
    user_name = await asyncio.to_thread(get_user_name, card_id)

    set_status(ctx, view_processing())
    await _speak_safe(announce_processing)

    await asyncio.to_thread(append_csv, user_name, action)

    now_ = datetime.now(JST)
    await asyncio.to_thread(
        send_attendance_message,
        user_name,
        action,
        at=now_,
        card_id=card_id,
    )

    set_status(ctx, view_done(action, now_))
    await _speak_safe(announce_done, action, now_.hour, now_.minute)


async def wait_and_record(ctx: AppContext, action: str) -> None:
    ctx.state.cancel_event.clear()
    set_busy(ctx, True)
    set_status(ctx, view_waiting())

    reader_error_displayed = False

    try:
        await _speak_safe(announce_touch_card)

        while True:
            if ctx.state.cancel_event.is_set():
                return

            if reader_error_displayed:
                await _wait_for_reader_recovery(ctx)
                if ctx.state.cancel_event.is_set():
                    return
                reader_error_displayed = False

            try:
                card_id = await asyncio.to_thread(get_uid)

                if is_debounced(card_id):
                    await asyncio.sleep(0.2)
                    continue

                await _record_attendance(ctx, action, card_id)
                return

            except NoReaderError:
                if not reader_error_displayed:
                    set_status(ctx, view_error(READER_ERROR_MESSAGE))
                    reader_error_displayed = True
                await asyncio.sleep(1.0)

            except (CardConnectionException, NoCardException):
                await asyncio.sleep(0.2)

            except Exception as e:
                set_status(ctx, view_error(f"エラー：{e!r}"))
                try:
                    await asyncio.to_thread(
                        speak_jp,
                        "エラーが発生しました。端末を確認してください。",
                    )
                except Exception:
                    pass
                await asyncio.sleep(1.0)
                set_status(ctx, view_waiting())

    finally:
        set_status(ctx, view_idle())
        set_busy(ctx, False)
