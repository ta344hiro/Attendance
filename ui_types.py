from __future__ import annotations

from dataclasses import dataclass
import flet as ft

from state import AppState


# UI部品
@dataclass
class Controls:
    title: ft.Text
    status_switcher: ft.AnimatedSwitcher

    time_info: ft.Text
    date_info: ft.Text
    temp_info: ft.Text

    checkin_btn: ft.Button
    checkout_btn: ft.Button
    cancel_btn: ft.Button
    log_btn: ft.Button

    nowcast_label: ft.Text
    nowcast_img: ft.Image

    zoom_text: ft.Text
    zoom_slider: ft.Slider
    btn_minus: ft.IconButton
    btn_plus: ft.IconButton
    zoom_bar: ft.Row

    info_card: ft.Container


# 各モジュールへの橋渡し
@dataclass
class AppContext:
    page: ft.Page
    state: AppState
    ui: Controls
