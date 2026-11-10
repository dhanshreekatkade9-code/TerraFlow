"""Weather adapter: Open-Meteo forecast -> one normalised schema, with provenance.

Owner: Dhanshree.
Sources returned: "live" (fresh API call), "cached" (last good call, timestamped),
"sample" (offline demo data - the UI MUST show a DEMO badge for this).

Backward compatible: get_weather() still returns (DataFrame, source_label).
New: get_weather_with_meta() returns the same data plus provenance fields.
"""
import json
from pathlib import Path
from datetime import date, datetime, timezone


import pandas as pd
import requests

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
REQUIRED = ["rain_mm", "tmax_c", "et0_mm"]
OPTIONAL = ["rain_prob_pct", "tmin_c"]
PROVIDER = "Open-Meteo (forecast / model output)"


def sample_weather(days=7):
    """Offline DEMO dataset. Never present this as live weather."""
    days = max(1, min(int(days), 16))
    base_dates = pd.date_range(pd.Timestamp.today().normalize(), periods=days).strftime("%Y-%m-%d")
    sample_rain = [0.0, 0.0, 2.0, 12.0, 0.0, 0.0, 0.0, 0.0, 5.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    sample_tmax = [36.0, 38.0, 35.0, 31.0, 34.0, 37.0, 39.0, 38.0, 33.0, 35.0, 36.0, 37.0, 38.0, 36.0, 35.0, 36.0]
    sample_et0 = [5.5, 5.8, 5.0, 3.5, 5.0, 5.6, 6.0, 5.7, 4.2, 4.8, 5.2, 5.5, 5.9, 5.6, 5.3, 5.4]
    return pd.DataFrame({
        "date": base_dates,
        "rain_mm": sample_rain[:days],
        "tmax_c": sample_tmax[:days],
        "et0_mm": sample_et0[:days],
    })


def clean(df):
    """Coerce to numbers, clip impossible values. Raises ValueError if a required
    value is missing - we do NOT silently turn a missing temperature into 0 C."""
    df = df.copy()
    for col in REQUIRED + OPTIONAL:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if df[REQUIRED].isna().any().any():
        raise ValueError("Forecast contains missing values for rain, temperature or ET0")
    df["rain_mm"] = df["rain_mm"].clip(lower=0.0)
    df["et0_mm"] = df["et0_mm"].clip(lower=0.0)
    if (df["tmax_c"].abs() > 60).any():
        raise ValueError("Forecast temperature out of plausible range")
    if "rain_prob_pct" in df.columns:
        df["rain_prob_pct"] = df["rain_prob_pct"].clip(0, 100)
    return df.reset_index(drop=True)


def _now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _cache_path(lat, lon):
    return CACHE_DIR / f"weather_{float(lat):.2f}_{float(lon):.2f}.json"


def _save_cache(lat, lon, df, meta):
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        payload = {"meta": meta, "records": json.loads(df.to_json(orient="records"))}
        _cache_path(lat, lon).write_text(json.dumps(payload), encoding="utf-8")
    except Exception as err:  # cache is a convenience; never crash for it
        print(f"Notice: could not write weather cache ({type(err).__name__}).")



def _load_cache(lat, lon, max_age_days=1):
    try:
        payload = json.loads(_cache_path(lat, lon).read_text(encoding="utf-8"))
        df, meta = clean(pd.DataFrame(payload["records"])), payload["meta"]
        start = datetime.strptime(meta["forecast_start"], "%Y-%m-%d").date()
        if (date.today() - start).days > max_age_days:
            return None
        return df, meta
    except Exception:
        return None


def _meta(df, source, lat, lon, timezone_name, retrieved_at, note="", current=None):
    return {
        "current": current or {},               # temperature_2m, relative_humidity_2m, wind_speed_10m (live only)
        "source": source,                       # live | cached | sample
        "provider": PROVIDER if source != "sample" else "Built-in DEMO data",
        "latitude": float(lat),
        "longitude": float(lon),
        "timezone": timezone_name,
        "retrieved_at": retrieved_at,
        "forecast_start": str(df["date"].iloc[0]),
        "forecast_end": str(df["date"].iloc[-1]),
        "note": note,
    }


def get_weather_with_meta(lat=18.52, lon=73.86, days=7, retries=1):
    """Returns {"df": DataFrame, "meta": dict}. Order tried: live -> cached -> sample."""
    days = max(1, min(int(days), 16))
    params = {
        "latitude": float(lat),
        "longitude": float(lon),
        "daily": "precipitation_sum,precipitation_probability_max,"
                 "temperature_2m_max,temperature_2m_min,et0_fao_evapotranspiration",
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        "timezone": "auto",
        "forecast_days": days,
    }
    headers = {"User-Agent": "TerraFlow/1.0 (Agricultural Decision Support)"}
    last_err = None
    for _ in range(retries + 1):
        try:
            r = requests.get("https://api.open-meteo.com/v1/forecast",
                             params=params, headers=headers, timeout=10)
            r.raise_for_status()
            body = r.json()
            daily = body["daily"]
            df = clean(pd.DataFrame({
                "date": daily["time"],
                "rain_mm": daily["precipitation_sum"],
                "rain_prob_pct": daily.get("precipitation_probability_max", [None] * len(daily["time"])),
                "tmax_c": daily["temperature_2m_max"],
                "tmin_c": daily.get("temperature_2m_min", [None] * len(daily["time"])),
                "et0_mm": daily["et0_fao_evapotranspiration"],
            }))
            meta = _meta(df, "live", lat, lon, body.get("timezone", "auto"), _now_iso(),
                         current=body.get("current") or {})
            _save_cache(lat, lon, df, meta)
            return {"df": df, "meta": meta}
        except Exception as err:
            last_err = err

    print(f"Notice: live weather unavailable ({type(last_err).__name__}).")
    cached = _load_cache(lat, lon)
    if cached:
        df, old = cached
        meta = dict(old, source="cached",
                    note=f"Live fetch failed; showing forecast fetched at {old.get('retrieved_at')}")
        return {"df": df, "meta": meta}

    df = sample_weather(days)
    return {"df": df, "meta": _meta(df, "sample", lat, lon, "local", _now_iso(),
                                    "DEMO DATA - live weather and cache unavailable")}


def get_weather(lat=18.52, lon=73.86, days=7):
    """Legacy contract used by app.py: (DataFrame, 'live' | 'cached' | 'sample')."""
    b = get_weather_with_meta(lat, lon, days)
    return b["df"], b["meta"]["source"]


def weather_summary(df):
    return {
        "total_rain_mm": round(float(df["rain_mm"].sum()), 1),
        "mean_tmax_c": round(float(df["tmax_c"].mean()), 1),
        "max_tmax_c": round(float(df["tmax_c"].max()), 1),
        "total_et0_mm": round(float(df["et0_mm"].sum()), 1),
        "rainy_days": int((df["rain_mm"] >= 1.0).sum()),
    }


if __name__ == "__main__":
    b = get_weather_with_meta(18.52, 73.86, 7)
    print(b["meta"])
    print(b["df"])
    print(weather_summary(b["df"]))