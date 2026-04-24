from __future__ import annotations

from datetime import datetime

import flet as ft

from config import ZOOM_MAX, ZOOM_MIN, ZOOM_NAMES
from state import AppState
from ui_types import AppContext, Controls


def card(content: ft.Control, *, padding: int = 12) -> ft.Container:
    return ft.Container(
        content=content,
        padding=padding,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.BLACK),
        border_radius=12,
    )


def build_controls(page: ft.Page, state: AppState) -> Controls:
    _ = page

    title = ft.Text("勤怠管理アプリ", size=36, weight=ft.FontWeight.BOLD)
    status_switcher = ft.AnimatedSwitcher(
        content=ft.Text("出勤または退勤を選んでください。", size=22),
        duration=300,
        transition=ft.AnimatedSwitcherTransition.SCALE,
    )

    time_info = ft.Text("", size=40, weight=ft.FontWeight.BOLD)
    date_info = ft.Text("", size=18, text_align=ft.TextAlign.CENTER)
    temp_info = ft.Text("取得待ち", size=18, text_align=ft.TextAlign.CENTER)

    checkin_btn = ft.Button(content="出勤", width=220, height=80)
    checkout_btn = ft.Button(content="退勤", width=220, height=80)
    cancel_btn = ft.Button(content="キャンセル", visible=False)
    log_btn = ft.Button(content="ログを見る", width=220, height=52)

    nowcast_label = ft.Text("", size=14, color=ft.Colors.GREY)
    nowcast_img = ft.Image(src="", fit=ft.BoxFit.CONTAIN, expand=True)

    zoom_text = ft.Text(ZOOM_NAMES[state.zoom_level], size=12, color=ft.Colors.GREY)
    zoom_slider = ft.Slider(
        min=ZOOM_MIN,
        max=ZOOM_MAX,
        divisions=ZOOM_MAX - ZOOM_MIN,
        value=state.zoom_level,
        width=180,
    )
    btn_minus = ft.IconButton(icon=ft.Icons.REMOVE)
    btn_plus = ft.IconButton(icon=ft.Icons.ADD)

    zoom_bar = ft.Row(
        controls=[btn_minus, zoom_slider, btn_plus, zoom_text],
        spacing=8,
        alignment=ft.MainAxisAlignment.END,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    info_card = card(
        ft.Column(
            controls=[
                ft.Container(content=time_info, alignment=ft.Alignment.CENTER),
                ft.Container(content=date_info, alignment=ft.Alignment.CENTER),
                ft.Container(content=temp_info, alignment=ft.Alignment.CENTER),
            ],
            spacing=6,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=16,
    )

    return Controls(
        title=title,
        status_switcher=status_switcher,
        time_info=time_info,
        date_info=date_info,
        temp_info=temp_info,
        checkin_btn=checkin_btn,
        checkout_btn=checkout_btn,
        cancel_btn=cancel_btn,
        log_btn=log_btn,
        nowcast_label=nowcast_label,
        nowcast_img=nowcast_img,
        zoom_text=zoom_text,
        zoom_slider=zoom_slider,
        btn_minus=btn_minus,
        btn_plus=btn_plus,
        zoom_bar=zoom_bar,
        info_card=info_card,
    )


def build_layout(ctx: AppContext) -> ft.Control:
    left = ft.Container(
        expand=1,
        padding=ft.padding.only(right=12),
        content=ft.Column(
            controls=[
                ctx.ui.title,
                ft.Container(height=12),
                ft.Container(
                    content=ctx.ui.status_switcher,
                    alignment=ft.Alignment.CENTER,
                    padding=10,
                ),
                ft.Container(height=20),
                ft.Row(
                    controls=[ctx.ui.checkin_btn, ctx.ui.checkout_btn],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=20,
                ),
                ft.Container(height=12),
                ft.Row(
                    controls=[ctx.ui.log_btn, ctx.ui.cancel_btn],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=20,
                ),
                ft.Container(height=20),
                ctx.ui.info_card,
                ft.Container(expand=True),
            ],
            spacing=0,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    right = ft.Container(
        expand=1,
        padding=ft.padding.only(left=12),
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("雨雲レーダー（実況）", size=18, weight=ft.FontWeight.BOLD),
                        ft.Container(expand=True),
                        ctx.ui.zoom_bar,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=8),
                ctx.ui.nowcast_label,
                ft.Container(
                    content=ctx.ui.nowcast_img,
                    alignment=ft.Alignment.CENTER,
                    expand=True,
                ),
            ],
            spacing=0,
            expand=True,
        ),
    )

    return ft.Row(
        controls=[left, right],
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
    )


def set_status(ctx: AppContext, control: ft.Control) -> None:
    ctx.ui.status_switcher.content = control
    ctx.page.update()


def set_busy(ctx: AppContext, value: bool) -> None:
    ctx.state.busy = value
    ctx.ui.checkin_btn.disabled = value
    ctx.ui.checkout_btn.disabled = value
    ctx.ui.log_btn.disabled = value
    ctx.ui.cancel_btn.visible = value
    ctx.page.update()


def refresh_zoom_ui(ctx: AppContext) -> None:
    lv = ctx.state.zoom_level
    ctx.ui.zoom_slider.value = lv
    ctx.ui.zoom_text.value = ZOOM_NAMES[lv]
    ctx.ui.btn_plus.disabled = lv >= ZOOM_MAX
    ctx.ui.btn_minus.disabled = lv <= ZOOM_MIN
    ctx.page.update()


def view_idle() -> ft.Control:
    return ft.Text("出勤または退勤を選んでください。", size=22)


def view_waiting() -> ft.Control:
    return ft.Row(
        [ft.Icon(ft.Icons.NFC, size=34), ft.Text("カードをタッチしてください", size=22)],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=12,
    )


def view_processing() -> ft.Control:
    return ft.Row(
        [ft.ProgressRing(), ft.Text("処理中です。しばらくお待ちください。", size=22)],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=12,
    )


def view_done(action: str, now_: datetime) -> ft.Control:
    label = "出勤記録" if action == "IN" else "退勤記録"
    return ft.Column(
        controls=[
            ft.Icon(ft.Icons.CHECK_CIRCLE, size=48),
            ft.Text(
                f"{label}：{now_.hour}:{now_.minute:02d}",
                size=28,
                weight=ft.FontWeight.BOLD,
                text_align=ft.TextAlign.CENTER,
            ),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=6,
    )


def view_error(message: str) -> ft.Control:
    return ft.Text(
        message,
        size=20,
        color=ft.Colors.RED,
        text_align=ft.TextAlign.CENTER,
    )


def build_logs_dialog(entries: list[dict[str, str]]) -> ft.AlertDialog:
    if not entries:
        content: ft.Control = ft.Container(
            content=ft.Text("まだログがありません。", size=18),
            padding=ft.padding.symmetric(vertical=8),
        )
    else:
        rows: list[ft.Control] = [
            ft.Row(
                controls=[
                    ft.Text("日時", weight=ft.FontWeight.BOLD, expand=5),
                    ft.Text("ユーザー", weight=ft.FontWeight.BOLD, expand=3),
                    ft.Text("区分", weight=ft.FontWeight.BOLD, expand=2),
                ]
            ),
            ft.Divider(),
        ]

        for entry in entries:
            rows.append(
                ft.Row(
                    controls=[
                        ft.Text(entry["timestamp"], expand=5),
                        ft.Text(entry["user_name"], expand=3),
                        ft.Text(entry["action"], expand=2),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.START,
                )
            )
            rows.append(ft.Divider(height=8))

        content = ft.Container(
            width=720,
            height=520,
            content=ft.ListView(controls=rows, spacing=0, padding=ft.padding.only(right=8)),
        )

    return ft.AlertDialog(
        modal=True,
        title=ft.Text("出退勤ログ"),
        content=content,
        actions=[ft.TextButton("閉じる")],
        actions_alignment=ft.MainAxisAlignment.END,
    )
