from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import requests

try:
    import config as _config
except Exception:
    _config = None


DEFAULT_USERNAME = "勤怠通知"
DEFAULT_ICON_EMOJI = ":credit_card:"
DEFAULT_TIMEOUT_SEC = 10.0
VALID_ACTIONS = {"IN": "出勤", "OUT": "退勤"}


class MattermostConfigError(RuntimeError):
    """Mattermost設定が不足しているときの例外。"""


class MattermostPostError(RuntimeError):
    """Mattermost送信に失敗したときの例外。"""


def _get_setting(name: str, default: Any = None) -> Any:
    """
    優先順位:
    1. 環境変数
    2. config.py
    3. default
    """
    env_value = os.getenv(name)
    if env_value not in (None, ""):
        return env_value

    if _config is not None and hasattr(_config, name):
        return getattr(_config, name)

    return default


def _get_webhook_url() -> str:
    url = _get_setting("MATTERMOST_WEBHOOK_URL", "")
    url = str(url).strip()
    if not url:
        raise MattermostConfigError(
            "MATTERMOST_WEBHOOK_URL が未設定です。"
            "環境変数または config.py に Incoming Webhook のURLを設定してください。"
        )
    return url


def send_mattermost_message(
    text: str,
    *,
    channel: str | None = None,
    username: str | None = None,
    icon_emoji: str | None = None,
    timeout: float | None = None,
) -> None:
    """
    Mattermost Incoming Webhook へメッセージを送信する。

    Parameters
    ----------
    text:
        投稿本文
    channel:
        投稿先チャンネル（省略時は設定値を使用）
    username:
        表示名（省略時は設定値または既定値を使用）
    icon_emoji:
        アイコン絵文字（省略時は設定値または既定値を使用）
    timeout:
        HTTPタイムアウト秒
    """
    if not str(text).strip():
        raise ValueError("text は空にできません")

    webhook_url = _get_webhook_url()

    resolved_channel = channel if channel is not None else _get_setting("MATTERMOST_CHANNEL", None)
    resolved_username = username if username is not None else _get_setting("MATTERMOST_USERNAME", DEFAULT_USERNAME)
    resolved_icon_emoji = icon_emoji if icon_emoji is not None else _get_setting("MATTERMOST_ICON_EMOJI", DEFAULT_ICON_EMOJI)

    resolved_timeout = timeout
    if resolved_timeout is None:
        raw_timeout = _get_setting("MATTERMOST_TIMEOUT_SEC", DEFAULT_TIMEOUT_SEC)
        resolved_timeout = float(raw_timeout)

    payload: dict[str, Any] = {"text": str(text)}
    if resolved_channel:
        payload["channel"] = str(resolved_channel)
    if resolved_username:
        payload["username"] = str(resolved_username)
    if resolved_icon_emoji:
        payload["icon_emoji"] = str(resolved_icon_emoji)

    try:
        response = requests.post(webhook_url, json=payload, timeout=resolved_timeout)
        response.raise_for_status()
    except requests.RequestException as e:
        raise MattermostPostError(f"Mattermost送信に失敗しました: {e}") from e


def build_attendance_message(
    user_name: str,
    action: str,
    *,
    at: datetime | None = None,
    card_id: str | None = None,
) -> str:
    """
    勤怠通知文を生成する。
    """
    action_key = str(action).strip().upper()
    if action_key not in VALID_ACTIONS:
        raise ValueError(f"action must be one of {set(VALID_ACTIONS)}, got: {action!r}")

    timestamp = (at or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    action_label = VALID_ACTIONS[action_key]
    name = str(user_name).strip() or "未登録ユーザー"

    if card_id and (name == "未登録ユーザー" or name.startswith("未登録ユーザー(")):
        return f"⚠️ {name} が{action_label}しました（card_id: {card_id}, {timestamp}）"

    return f"{name}さんが{action_label}しました（{timestamp}）"


def send_attendance_message(
    user_name: str,
    action: str,
    *,
    at: datetime | None = None,
    card_id: str | None = None,
    channel: str | None = None,
) -> None:
    """
    勤怠通知用の整形済みメッセージを Mattermost に送る。
    """
    text = build_attendance_message(user_name, action, at=at, card_id=card_id)
    send_mattermost_message(text, channel=channel)


if __name__ == "__main__":
    # 動作確認用:
    # 事前に MATTERMOST_WEBHOOK_URL を設定してから実行してください。
    send_mattermost_message("Mattermost連携テストです。")
