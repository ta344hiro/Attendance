from __future__ import annotations

import base64
import io
import math
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw

JST = ZoneInfo("Asia/Tokyo")
UTC = timezone.utc

# 対角（参考点）：神保町（赤）・登戸（青）
JIMBOCHO = (35.695963, 139.758061)  # lat, lon
NOBORITO = (35.620764, 139.570135)  # lat, lon

# 背景地図（国土地理院 標準地図）
GSI_STD = "https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png"

# JMA nowcast
NOWC_TARGET_N1_URL = "https://www.jma.go.jp/bosai/jmatile/data/nowc/targetTimes_N1.json"
NOWC_TILE_URL_FMT = (
    "https://www.jma.go.jp/bosai/jmatile/data/nowc/{basetime}/none/{validtime}/surf/hrpns/{z}/{x}/{y}.png"
)

TILE = 256

# ---- 3段階ズーム----
ZOOM_LEVELS = {
    0: {"name": "本州", "z": 6, "ne": (42.5, 143.8), "sw": (33.0, 131.0)},
    1: {"name": "関東", "z": 8, "ne": (36.8, 141.2), "sw": (34.7, 138.7)},
    2: {"name": "最大", "z": 10, "ne": JIMBOCHO, "sw": NOBORITO},  # 神保町〜登戸
}

ASPECT_BASE_LEVEL = 2

CACHE_BASE = Path.home() / "attendance" / "cache"
CACHE_GSI = CACHE_BASE / "gsi_std"
CACHE_NOWC = CACHE_BASE / "jma_nowc_hrpns"
CACHE_NOWC_RETENTION = timedelta(hours=3)
CACHE_CLEANUP_INTERVAL = timedelta(minutes=30)
CACHE_GSI.mkdir(parents=True, exist_ok=True)
CACHE_NOWC.mkdir(parents=True, exist_ok=True)

_LAST_NOWCAST_CACHE_CLEANUP: datetime | None = None


def _global_pixel(lat: float, lon: float, z: int) -> tuple[float, float]:
    lat_rad = math.radians(lat)
    n = 2**z
    x = (lon + 180.0) / 360.0 * n * TILE
    y = (1.0 - (math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi)) / 2.0 * n * TILE
    return x, y


def _clamp_tile(v: int, z: int) -> int:
    max_i = (2**z) - 1
    return max(0, min(max_i, v))


def _fetch_png(url: str, timeout: int = 15) -> Image.Image:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGBA")


def _fetch_cached(root: Path, z: int, x: int, y: int, url: str, *, allow_missing: bool = False) -> Image.Image:
    d = root / str(z) / str(x)
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{y}.png"
    if f.exists():
        return Image.open(f).convert("RGBA")

    try:
        img = _fetch_png(url)
        img.save(f)
        return img
    except requests.HTTPError:
        if allow_missing:
            # 無いタイルは透明扱い（雨雲レイヤで稀に発生した時の保険）
            return Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
        raise


def _parse_nowcast_cache_time(name: str) -> datetime | None:
    try:
        return datetime.strptime(name, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def cleanup_nowcast_cache(
    retention: timedelta = CACHE_NOWC_RETENTION,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> int:
    global _LAST_NOWCAST_CACHE_CLEANUP

    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    else:
        current = current.astimezone(UTC)

    if (
        not force
        and _LAST_NOWCAST_CACHE_CLEANUP is not None
        and current - _LAST_NOWCAST_CACHE_CLEANUP < CACHE_CLEANUP_INTERVAL
    ):
        return 0

    _LAST_NOWCAST_CACHE_CLEANUP = current
    cutoff = current - retention
    removed = 0

    for path in CACHE_NOWC.iterdir():
        if not path.is_dir():
            continue

        cached_at = _parse_nowcast_cache_time(path.name)
        if cached_at is None:
            try:
                cached_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            except OSError:
                continue

        if cached_at >= cutoff:
            continue

        try:
            shutil.rmtree(path)
            removed += 1
        except OSError:
            pass

    return removed


@dataclass(frozen=True)
class NowcastFrame:
    basetime: str
    validtime: str

    def validtime_jst(self) -> datetime:
        dt_utc = datetime.strptime(self.validtime, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        return dt_utc.astimezone(JST)


def get_latest_n1_frame(timeout: int = 10) -> NowcastFrame:
    n1 = requests.get(NOWC_TARGET_N1_URL, timeout=timeout).json()
    latest = n1[0]
    cleanup_nowcast_cache()
    return NowcastFrame(basetime=latest["basetime"], validtime=latest["validtime"])


def build_nowcast_panel_png(
    *,
    frame: NowcastFrame,
    zoom_level: int = 0,
    opacity: float = 0.65,
    out_width: int = 700,
) -> tuple[bytes, str]:
    zinfo = ZOOM_LEVELS.get(int(zoom_level), ZOOM_LEVELS[0])
    z = zinfo["z"]
    lat_ne, lon_ne = zinfo["ne"]
    lat_sw, lon_sw = zinfo["sw"]

    # N1ラベル（JST）
    dt_jst = frame.validtime_jst()
    label = f"雨雲レーダー（実況） {dt_jst:%Y-%m-%d %H:%M}（JST） / {zinfo['name']}"

    # bboxをglobal pixelに
    x_ne, y_ne = _global_pixel(lat_ne, lon_ne, z)
    x_sw, y_sw = _global_pixel(lat_sw, lon_sw, z)

    left = min(x_sw, x_ne)
    right = max(x_sw, x_ne)
    top = min(y_ne, y_sw)
    bottom = max(y_ne, y_sw)

    PAD = 32
    world_px = (2 ** z) * TILE

    left = max(0, left - PAD)
    right = min(world_px - 1, right + PAD)
    top = max(0, top - PAD)
    bottom = min(world_px - 1, bottom + PAD)

    target_aspect = _get_target_aspect()
    left, right, top, bottom = _adjust_bbox_aspect(left, right, top, bottom, z, target_aspect)

    x0 = _clamp_tile(int(left // TILE), z)
    x1 = _clamp_tile(int((right - 1) // TILE), z)
    y0 = _clamp_tile(int(top // TILE), z)
    y1 = _clamp_tile(int((bottom - 1) // TILE), z)

    cols = x1 - x0 + 1
    rows = y1 - y0 + 1
    canvas = Image.new("RGBA", (cols * TILE, rows * TILE), (0, 0, 0, 0))

    # タイル合成（GSI + nowcast）
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            base = _fetch_cached(CACHE_GSI, z, tx, ty, GSI_STD.format(z=z, x=tx, y=ty))

            nowc_root = CACHE_NOWC / frame.validtime
            nowc = _fetch_cached(
                nowc_root,
                z,
                tx,
                ty,
                NOWC_TILE_URL_FMT.format(basetime=frame.basetime, validtime=frame.validtime, z=z, x=tx, y=ty),
                allow_missing=True,
            )

            if opacity < 1.0:
                r, g, b, a = nowc.split()
                a = a.point(lambda v: int(v * opacity))
                nowc = Image.merge("RGBA", (r, g, b, a))

            merged = Image.alpha_composite(base, nowc)
            canvas.paste(merged, ((tx - x0) * TILE, (ty - y0) * TILE))

    # crop
    crop_l = int(left - x0 * TILE)
    crop_t = int(top - y0 * TILE)
    crop_r = int(right - x0 * TILE)
    crop_b = int(bottom - y0 * TILE)
    img = canvas.crop((crop_l, crop_t, crop_r, crop_b))

    # リサイズ
    if out_width and img.size[0] != out_width:
        scale = out_width / img.size[0]
        out_h = max(1, int(img.size[1] * scale))
        img = img.resize((out_width, out_h), Image.LANCZOS)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue(), label

_TARGET_ASPECT = None

def _get_target_aspect() -> float:
    """
    最大ズーム（ZOOM_LEVELS[0]）の bbox を基準にしたアスペクト比を返す。
    """
    global _TARGET_ASPECT
    if _TARGET_ASPECT is not None:
        return _TARGET_ASPECT

    z0 = ZOOM_LEVELS[0]["z"]
    lat_ne, lon_ne = ZOOM_LEVELS[0]["ne"]
    lat_sw, lon_sw = ZOOM_LEVELS[0]["sw"]

    x_ne, y_ne = _global_pixel(lat_ne, lon_ne, z0)
    x_sw, y_sw = _global_pixel(lat_sw, lon_sw, z0)

    left = min(x_sw, x_ne)
    right = max(x_sw, x_ne)
    top = min(y_ne, y_sw)
    bottom = max(y_ne, y_sw)

    # build_nowcast_panel_png と同じPADを想定（後述のPADと合わせてください）
    PAD = 32
    w = (right - left) + PAD * 2
    h = (bottom - top) + PAD * 2
    _TARGET_ASPECT = (w / h) if h > 0 else 1.0
    HEIGHT_GAIN = 0.75
    _TARGET_ASPECT *= HEIGHT_GAIN

    return _TARGET_ASPECT


def _adjust_bbox_aspect(left: float, right: float, top: float, bottom: float, z: int, target_aspect: float):
    """
    bbox の縦横比が target_aspect になるように、短い辺を広げる（中心は維持）。
    """
    cx = (left + right) / 2.0
    cy = (top + bottom) / 2.0
    w = right - left
    h = bottom - top
    if w <= 0 or h <= 0:
        return left, right, top, bottom

    cur = w / h
    if cur > target_aspect:
        # 横が広い → 縦を広げる
        new_h = w / target_aspect
        new_w = w
    else:
        # 縦が広い → 横を広げる
        new_w = h * target_aspect
        new_h = h

    nl = cx - new_w / 2.0
    nr = cx + new_w / 2.0
    nt = cy - new_h / 2.0
    nb = cy + new_h / 2.0

    # 世界範囲に収める（WebMercatorのglobal pixel範囲）
    world_px = (2**z) * TILE
    # x方向
    if nl < 0:
        nr -= nl
        nl = 0
    if nr > world_px - 1:
        shift = nr - (world_px - 1)
        nl -= shift
        nr = world_px - 1
        if nl < 0:
            nl = 0
    # y方向
    if nt < 0:
        nb -= nt
        nt = 0
    if nb > world_px - 1:
        shift = nb - (world_px - 1)
        nt -= shift
        nb = world_px - 1
        if nt < 0:
            nt = 0

    return nl, nr, nt, nb


def build_nowcast_panel_base64(**kwargs) -> tuple[str, str]:
    png, label = build_nowcast_panel_png(**kwargs)
    return base64.b64encode(png).decode("ascii"), label
