from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import math
import requests
from PIL import Image

from config import JST

import asyncio

from ui_types import AppContext
from nowcast_renderer import build_nowcast_panel_base64, get_latest_n1_frame

# === 位置（千代田区）===
LAT = 35.6938
LON = 139.7530

# === 気象庁 bosai endpoints ===
AMEDAS_TABLE_URL = "https://www.jma.go.jp/bosai/amedas/const/amedastable.json"
AMEDAS_LATEST_TIME_URL = "https://www.jma.go.jp/bosai/amedas/data/latest_time.txt"
AMEDAS_MAP_URL_FMT = "https://www.jma.go.jp/bosai/amedas/data/map/{stamp}.json"
NOWC_TARGET_N1_URL = "https://www.jma.go.jp/bosai/jmatile/data/nowc/targetTimes_N1.json"
NOWC_TARGET_N2_URL = "https://www.jma.go.jp/bosai/jmatile/data/nowc/targetTimes_N2.json"
NOWC_TILE_URL_FMT = (
    "https://www.jma.go.jp/bosai/jmatile/data/nowc/{basetime}/none/{validtime}/surf/hrpns/{z}/{x}/{y}.png"
)
OSM_TILE_URL_FMT = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

UTC = timezone.utc

def _parse_utc_yyyymmddhhmmss(s: str) -> datetime:
    return datetime.strptime(s, "%Y%m%d%H%M%S").replace(tzinfo=UTC)

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))

def _latlon_to_tile_and_pixel(lat: float, lon: float, z: int) -> tuple[int, int, int, int]:
    """
    WebMercator tile:
    returns (x_tile, y_tile, px, py) where px/py is 0-255 pixel in tile
    """
    lat_rad = math.radians(lat)
    n = 2**z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - (math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi)) / 2.0 * n

    xt, yt = int(x), int(y)
    px = int((x - xt) * 256)
    py = int((y - yt) * 256)
    px = max(0, min(255, px))
    py = max(0, min(255, py))
    return xt, yt, px, py


# 軽いキャッシュ（無駄アクセス防止）
_AMEDAS_TABLE_CACHE: list["AmedasStation"] | None = None
_LAST_TEMP_CACHE = {"ts": 0.0, "temp": None, "obs": None, "name": None}
_LAST_RAIN_CACHE = {"ts": 0.0, "result": None, "first_dt": None}


@dataclass
class AmedasStation:
    code: str
    name: str
    lat: float
    lon: float

def _load_amedas_table() -> list[AmedasStation]:
    global _AMEDAS_TABLE_CACHE
    if _AMEDAS_TABLE_CACHE is not None:
        return _AMEDAS_TABLE_CACHE

    js = requests.get(AMEDAS_TABLE_URL, timeout=10).json()
    stations: list[AmedasStation] = []
    for code, v in js.items():
        lat = float(v["lat"][0]) + float(v["lat"][1]) / 60.0
        lon = float(v["lon"][0]) + float(v["lon"][1]) / 60.0
        name = v.get("kjName") or v.get("enName") or str(code)
        stations.append(AmedasStation(code=str(code), name=name, lat=lat, lon=lon))

    _AMEDAS_TABLE_CACHE = stations
    return stations


def _latest_amedas_stamp() -> tuple[str, datetime]:
    txt = requests.get(AMEDAS_LATEST_TIME_URL, timeout=10).text.strip()
    obs = datetime.fromisoformat(txt)
    stamp = obs.strftime("%Y%m%d%H%M%S")
    return stamp, obs


def get_current_temp_amedas(lat: float = LAT, lon: float = LON) -> tuple[float, datetime, str]:
    """
    (気温[℃], 観測時刻, 観測所名)
    """
    now_ts = datetime.now(JST).timestamp()
    if _LAST_TEMP_CACHE["temp"] is not None and (now_ts - _LAST_TEMP_CACHE["ts"]) < 600:
        return _LAST_TEMP_CACHE["temp"], _LAST_TEMP_CACHE["obs"], _LAST_TEMP_CACHE["name"]

    stations = _load_amedas_table()
    stamp, obs = _latest_amedas_stamp()
    data = requests.get(AMEDAS_MAP_URL_FMT.format(stamp=stamp), timeout=15).json()

    stations_sorted = sorted(stations, key=lambda s: _haversine_km(lat, lon, s.lat, s.lon))
    for st in stations_sorted[:50]:
        rec = data.get(st.code)
        if not rec:
            continue
        temp = rec.get("temp")
        if isinstance(temp, list) and temp and temp[0] is not None:
            t = float(temp[0])
            _LAST_TEMP_CACHE.update({"ts": now_ts, "temp": t, "obs": obs, "name": st.name})
            return t, obs, st.name

    raise RuntimeError("近傍のアメダス観測所で気温が取得できませんでした")


def _tile_has_precip_at(lat: float, lon: float, basetime: str, validtime: str) -> bool:
    z = 10
    xt, yt, px, py = _latlon_to_tile_and_pixel(lat, lon, z)
    url = NOWC_TILE_URL_FMT.format(basetime=basetime, validtime=validtime, z=z, x=xt, y=yt)

    r = requests.get(url, timeout=10)
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)).convert("RGBA")

    # 点ピンポイントは外れやすいので 11x11 で見る
    for dy in range(-5, 6):
        for dx in range(-5, 6):
            x = max(0, min(255, px + dx))
            y = max(0, min(255, py + dy))
            *_, a = img.getpixel((x, y))
            if a != 0:
                return True
    return False


def will_rain_within_1h_by_nowcast(
    lat: float = LAT,
    lon: float = LON,
    step_minutes: int = 10,
) -> tuple[bool, datetime | None]:
    """
    (降る?, 最初に降りそうな時刻[JST] or None)
    - まず N1(実況) で「今降ってるか」を見る
    - 次に N2(予報) で「今後1時間」を見る
    """
    now_ts = datetime.now(JST).timestamp()
    if _LAST_RAIN_CACHE["result"] is not None and (now_ts - _LAST_RAIN_CACHE["ts"]) < 300:
        return _LAST_RAIN_CACHE["result"], _LAST_RAIN_CACHE["first_dt"]

    now_jst = datetime.now(JST)
    end_jst = now_jst + timedelta(hours=1)

    # 1) N1（実況）
    try:
        n1 = requests.get(NOWC_TARGET_N1_URL, timeout=10).json()
        latest = n1[0]
        bt = latest["basetime"]
        vt = latest["validtime"]
        if _tile_has_precip_at(lat, lon, bt, vt):
            first_dt = _parse_utc_yyyymmddhhmmss(vt).astimezone(JST)
            _LAST_RAIN_CACHE.update({"ts": now_ts, "result": True, "first_dt": first_dt})
            return True, first_dt
    except Exception:
        pass

    # 2) N2（予報）
    frames = requests.get(NOWC_TARGET_N2_URL, timeout=10).json()

    latest_base = max(f["basetime"] for f in frames)
    cand = [f for f in frames if f["basetime"] == latest_base]
    cand.sort(key=lambda f: f["validtime"])

    selected: list[tuple[str, str, datetime]] = []
    last_added: datetime | None = None

    for f in cand:
        vt_jst = _parse_utc_yyyymmddhhmmss(f["validtime"]).astimezone(JST)
        if vt_jst < now_jst:
            continue
        if vt_jst > end_jst:
            continue
        if last_added is None or (vt_jst - last_added) >= timedelta(minutes=step_minutes):
            selected.append((latest_base, f["validtime"], vt_jst))
            last_added = vt_jst

    first_rain: datetime | None = None
    for bt, vt, vt_jst in selected:
        if _tile_has_precip_at(lat, lon, bt, vt):
            first_rain = vt_jst
            break

    result = first_rain is not None
    _LAST_RAIN_CACHE.update({"ts": now_ts, "result": result, "first_dt": first_rain})
    return result, first_rain


async def render_nowcast(ctx: AppContext, refresh_frame: bool) -> None:
    async with ctx.state.nowcast_lock:
        try:
            if refresh_frame or ctx.state.nowcast_frame is None:
                ctx.state.nowcast_frame = await asyncio.to_thread(get_latest_n1_frame)
            
            frame = ctx.state.nowcast_frame
            if frame is None:
                raise ValueError("雨雲データを取得できませんでした。")

            w = ctx.page.width or 1200
            out_w = max(360, int(w * 0.48) - 48)

            b64, label = await asyncio.to_thread(
                build_nowcast_panel_base64,
                frame=ctx.state.nowcast_frame,
                zoom_level=ctx.state.zoom_level,
                opacity=0.65,
                out_width=out_w,
            )

            ctx.ui.nowcast_img.src = f"data:image/png;base64,{b64}"
            ctx.ui.nowcast_label.value = label
        
        except Exception as e:
            ctx.ui.nowcast_label.value = f"雨雲レーダー取得失敗: {e!r}"

        ctx.page.update()