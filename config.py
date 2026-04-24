#config.py
from __future__ import annotations

from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

UPDATE_MIN = 5

TEMP_UPDATE_MIN = UPDATE_MIN
NOWCAST_UPDATE_MIN = UPDATE_MIN

MATTERMOST_WEBHOOK_URL = ""
MATTERMOST_CHANNEL = None          
MATTERMOST_USERNAME = "勤怠通知"
MATTERMOST_ICON_EMOJI = ":credit_card:"
MATTERMOST_TIMEOUT_SEC = 10

ZOOM_MIN = 0
ZOOM_MAX = 2
ZOOM_NAMES = ["本州", "関東", "最寄周辺"]

DEFAULT_ZOOM_LEVEL= ZOOM_MAX

if len(ZOOM_NAMES) != (ZOOM_MAX - ZOOM_MIN + 1):
    raise ValueError("ZOOM_NAMESの数がZOOM_MIN/ZOOM_MAXと一致していません。")

CARD_USER_MAP = {}
UNKNOWN_USER_LABEL = "未登録ユーザー"

try:
    from config_local import CARD_USER_MAP as LOCAL_CARD_USER_MAP
except ImportError:
    LOCAL_CARD_USER_MAP = {}

CARD_USER_MAP.update(LOCAL_CARD_USER_MAP)