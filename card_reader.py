from __future__ import annotations

import csv
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from smartcard.System import readers

from config import JST, CARD_USER_MAP, UNKNOWN_USER_LABEL

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

CSV_FILE = LOG_DIR / "attendance.csv"
LAST_TAP_FILE = LOG_DIR / "last_tap.txt"
DEBOUNCE_SEC = 2.0

VALID_ACTIONS = {"IN", "OUT"}
ACTION_LABELS = {"IN": "出勤", "OUT": "退勤"}


class NoReaderError(RuntimeError):
    pass


def normalize_card_id(card_id: str) -> str:
    return str(card_id).strip().upper()


def get_user_name(card_id: str) -> str:
    normalized = normalize_card_id(card_id)
    return CARD_USER_MAP.get(normalized, UNKNOWN_USER_LABEL)


def now_str() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")


def ensure_csv_header() -> None:
    # CSV が存在しない、または空ファイルならヘッダを作る
    if (not CSV_FILE.exists()) or CSV_FILE.stat().st_size == 0:
        with CSV_FILE.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "user_name", "action"])


def append_csv(user_name: str, action: str) -> None:
    if action not in VALID_ACTIONS:
        raise ValueError(f"action must be one of {VALID_ACTIONS}, got:{action!r}")

    ensure_csv_header()

    with CSV_FILE.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([now_str(), str(user_name).strip() or UNKNOWN_USER_LABEL, action])


def read_recent_logs(limit: int = 50) -> list[dict[str, str]]:
    if limit <= 0:
        return []

    if not CSV_FILE.exists() or CSV_FILE.stat().st_size == 0:
        return []

    entries: list[dict[str, str]] = []
    with CSV_FILE.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            timestamp = (row.get("timestamp") or "").strip()
            action = (row.get("action") or "").strip().upper()
            user_name = (row.get("user_name") or "").strip()

            # 旧形式 (timestamp, card_id, action) からも読めるようにする
            if not user_name:
                card_id = (row.get("card_id") or "").strip()
                if card_id:
                    user_name = get_user_name(card_id)

            if not user_name:
                user_name = UNKNOWN_USER_LABEL

            action_label = ACTION_LABELS.get(action, action or "不明")

            if not timestamp:
                continue

            entries.append(
                {
                    "timestamp": timestamp,
                    "user_name": user_name,
                    "action": action_label,
                }
            )

    entries.reverse()
    return entries[:limit]


def pick_reader() -> Any:
    rs = readers()
    if not rs:
        raise NoReaderError("リーダーが見つかりません(pcscd/接続を確認)")

    # RC-S300っぽい名前を優先（無ければ先頭）
    priority_keywords = ("RC-S300", "FeliCa", "Sony")
    for r in rs:
        name = str(r)
        if any(key in name for key in priority_keywords):
            return r

    return rs[0]


def get_uid() -> str:
    r = pick_reader()
    conn = r.createConnection()
    try:
        conn.connect()

        get_uid_apdu = [0xFF, 0xCA, 0x00, 0x00, 0x00]
        data, sw1, sw2 = conn.transmit(get_uid_apdu)

        if (sw1, sw2) != (0x90, 0x00):
            raise RuntimeError(f"UID取得失敗: SW1SW2={sw1:02X}{sw2:02X}")

        return "".join(f"{b:02X}" for b in data)

    finally:
        try:
            conn.disconnect()
        except Exception:
            pass


def is_debounced(card_id: str) -> bool:
    card_id = normalize_card_id(card_id)
    now = time.time()

    if not LAST_TAP_FILE.exists():
        LAST_TAP_FILE.write_text(f"{card_id},{now}", encoding="utf-8")
        return False

    try:
        raw = LAST_TAP_FILE.read_text(encoding="utf-8").strip().split(",")
        last_id, last_ts = raw[0], float(raw[1])
    except Exception:
        LAST_TAP_FILE.write_text(f"{card_id},{now}", encoding="utf-8")
        return False

    if card_id == last_id and (now - last_ts) < DEBOUNCE_SEC:
        return True

    LAST_TAP_FILE.write_text(f"{card_id},{now}", encoding="utf-8")
    return False
