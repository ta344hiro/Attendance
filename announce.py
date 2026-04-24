from __future__ import annotations

import io
import math
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from PIL import Image, ImageDraw

from config import JST

# === OpenJTalk 設定 ===
OPENJTALK_DIC = "/var/lib/mecab/dic/open-jtalk/naist-jdic"
VOICE = "/usr/share/hts-voice/mei/mei_normal.htsvoice"

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


def speak_jp(text: str) -> None:
    """日本語音声を再生"""
    with tempfile.NamedTemporaryFile(suffix=".wav") as f:
        subprocess.run(
            ["open_jtalk", "-x", OPENJTALK_DIC, "-m", VOICE, "-ow", f.name],
            input=text.encode("utf-8"),
            check=True,
        )
        subprocess.run(["aplay", f.name], check=True)


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

_LAST_RAIN_CACHE = {
    "ts": 0.0,
    "will_rain": None,
    "is_raining_now": None,
    "first_dt": None,
}

def will_rain_within_1h_by_nowcast(
    lat: float = LAT,
    lon: float = LON,
    step_minutes: int = 10,
    radius_km: float = 1.0,
) -> tuple[bool, bool, datetime | None]:
    """
    戻り値:
      (will_rain, is_raining_now, first_dt)

    - is_raining_now:
        現在、基準地点から半径radius_km以内で降っているか
    - will_rain:
        今後1時間以内に降るか（今すでに降っている場合も True）
    - first_dt:
        最初に降る時刻
        すでに降っている場合は「現在の実況フレーム時刻」
    """
    now_ts = datetime.now(JST).timestamp()
    if (
        _LAST_RAIN_CACHE["will_rain"] is not None
        and (now_ts - _LAST_RAIN_CACHE["ts"]) < 300
    ):
        return (
            _LAST_RAIN_CACHE["will_rain"],
            _LAST_RAIN_CACHE["is_raining_now"],
            _LAST_RAIN_CACHE["first_dt"],
        )

    now_jst = datetime.now(JST)
    end_jst = now_jst + timedelta(hours=1)

    # 1) N1（実況）
    try:
        n1 = requests.get(NOWC_TARGET_N1_URL, timeout=10).json()
        latest = n1[0]
        bt = latest["basetime"]
        vt = latest["validtime"]

        if _tile_has_precip_at(lat, lon, bt, vt, radius_km=radius_km):
            first_dt = _parse_utc_yyyymmddhhmmss(vt).astimezone(JST)
            _LAST_RAIN_CACHE.update(
                {
                    "ts": now_ts,
                    "will_rain": True,
                    "is_raining_now": True,
                    "first_dt": first_dt,
                }
            )
            return True, True, first_dt
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
        if _tile_has_precip_at(lat, lon, bt, vt, radius_km=radius_km):
            first_rain = vt_jst
            break

    result = first_rain is not None
    _LAST_RAIN_CACHE.update(
        {
            "ts": now_ts,
            "will_rain": result,
            "is_raining_now": False,
            "first_dt": first_rain,
        }
    )
    return result, False, first_rain

def announce_touch_card() -> None:
    speak_jp("カードをタッチしてください。")


def announce_processing() -> None:
    speak_jp("処理中です。しばらくお待ちください。")


def announce_done(action: str, hour: int | None = None, minute: int | None = None) -> None:
    now = datetime.now(JST)
    h = now.hour if hour is None else hour
    m = now.minute if minute is None else minute

    text = f"記録を完了しました。現在の時刻は{h}時{m}分です。"

    if action == "IN":
        text += "今日も一日頑張りましょう。"
        speak_jp(text)
        return

    text += "今日も一日お疲れ様でした。"

    try:
        will_rain, is_raining_now, first_dt = will_rain_within_1h_by_nowcast(
            lat=LAT,
            lon=LON,
            radius_km=1.0,
        )

        if is_raining_now:
            text += "現在、雨が降っています。傘を忘れずお持ちください。"
        elif will_rain:
            text += "この先、雨が降る予定です。傘を忘れずお持ちください。"
    except Exception:
        pass

    speak_jp(text)


def debug_nowcast_point(lat: float = LAT, lon: float = LON) -> None:
    n1 = requests.get(NOWC_TARGET_N1_URL, timeout=10).json()
    latest = n1[0]
    bt = latest["basetime"]
    vt = latest["validtime"]

    z = 10
    xt, yt, px, py = _latlon_to_tile_and_pixel(lat, lon, z)
    url = NOWC_TILE_URL_FMT.format(basetime=bt, validtime=vt, z=z, x=xt, y=yt)

    r = requests.get(url, timeout=10)
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)).convert("RGBA")

    a_mat = []
    for dy in (-1, 0, 1):
        row = []
        for dx in (-1, 0, 1):
            x = max(0, min(255, px + dx))
            y = max(0, min(255, py + dy))
            *_, a = img.getpixel((x, y))
            row.append(a)
        a_mat.append(row)

    print("N1 basetime:", bt, "validtime:", vt)
    print("tile z/x/y:", z, xt, yt, "pixel:", px, py)
    print("alpha 3x3:", a_mat)
    print("rain? (any alpha!=0):", any(a != 0 for row in a_mat for a in row))


def dump_nowcast_tile_with_basemap(
    lat: float = LAT,
    lon: float = LON,
    radius_px: int = 5,
    z: int = 10,
    opacity: float = 0.65,
    out_dir: str = "debug_nowcast",
) -> None:
    os.makedirs(out_dir, exist_ok=True)

    n1 = requests.get(NOWC_TARGET_N1_URL, timeout=10).json()
    latest = n1[0]
    bt = latest["basetime"]
    vt = latest["validtime"]

    xt, yt, px, py = _latlon_to_tile_and_pixel(lat, lon, z)

    now_url = NOWC_TILE_URL_FMT.format(basetime=bt, validtime=vt, z=z, x=xt, y=yt)
    base_url = OSM_TILE_URL_FMT.format(z=z, x=xt, y=yt)

    rb = requests.get(base_url, timeout=10)
    rb.raise_for_status()
    base = Image.open(io.BytesIO(rb.content)).convert("RGBA")

    rn = requests.get(now_url, timeout=10)
    rn.raise_for_status()
    nowc = Image.open(io.BytesIO(rn.content)).convert("RGBA")

    if opacity < 1.0:
        r, g, b, a = nowc.split()
        a = a.point(lambda v: int(v * opacity))
        nowc = Image.merge("RGBA", (r, g, b, a))

    merged = Image.alpha_composite(base, nowc)

    draw = ImageDraw.Draw(merged)
    x0 = max(0, px - radius_px)
    y0 = max(0, py - radius_px)
    x1 = min(255, px + radius_px)
    y1 = min(255, py + radius_px)
    draw.rectangle([x0, y0, x1, y1], outline=(255, 0, 0, 255), width=2)
    draw.ellipse([px - 2, py - 2, px + 2, py + 2], fill=(255, 0, 0, 255))

    out_path = os.path.join(out_dir, f"map_nowc_{bt}_{vt}_z{z}_{xt}_{yt}_px{px}_py{py}.png")
    merged.convert("RGB").save(out_path)

    print("N1 basetime:", bt, "validtime:", vt)
    print("tile z/x/y:", z, xt, yt, "pixel:", px, py, "radius:", radius_px)
    print("base:", base_url)
    print("nowc:", now_url)
    print("saved:", out_path)