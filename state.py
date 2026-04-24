from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from config import DEFAULT_ZOOM_LEVEL
from nowcast_renderer import NowcastFrame

#状態変数
@dataclass
class AppState:
    #勤怠処理中フラグ(ボタン無効化などに使用)
    busy: bool = False

    #キャンセル通知
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    
    #雨雲ズーム
    zoom_level: int = DEFAULT_ZOOM_LEVEL
    
    #現在表示中の雨雲データの時刻情報
    nowcast_frame: Optional[NowcastFrame] = None
    
    #雨雲描画更新の同時実行防止
    nowcast_lock: asyncio.Lock = field(default_factory=asyncio.Lock)