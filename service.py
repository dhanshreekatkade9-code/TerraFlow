"""Glue between the website/API and Arya's engine. No web framework in here, so it
is easy to unit-test.

Rule: every irrigation number comes from engine.plan_week(). This file only
(1) checks the inputs, (2) turns farmer inputs into engine inputs, and
(3) applies the farmer's documented manual adjustments (crop stress, mulch,
water availability) that the website's form promises.
Unknown crop / soil / method values are REJECTED, never replaced by a default.
"""
from datetime import date, datetime

import pandas as pd

import engine
from weather import get_weather_with_meta, sample_weather, _now_iso

ACRE_M2 = 4046.86                     # 1 mm over 1 acre = 4046.86 litres
KW_PER_HP = 0.746                     # same constant the engine uses
LANGUAGES = {"en": "English", "mr": "Marathi", "hi": "Hindi",
             "english": "English", "marathi": "Marathi", "hindi": "Hindi"}
METHODS = ("flood", "sprinkler", "drip")

# Labels shown on the website's "Manual Field Update" form.
SOIL_FEEL = {"dry_cracked": 16.0, "slightly_moist": 26.0, "good_ball": 34.0, "wet_sticky": 45.0}
CROP_STRESS = {"normal": 1.00, "mild_wilt": 1.10, "heat_roll": 1.20, "yellow_wet": 0.70}
MULCH_EVAP_CUT = {"none": 0.00, "organic": 0.15, "plastic": 0.25}
POWER_SLOTS = {"day": "6:00 AM - 10:00 AM", "night": "10:00 PM - 5:00 AM",
               "solar": "8:30 AM - 4:00 PM", "afternoon": "12:00 PM - 4:00 PM"}
WATER_AVAIL = (1.0, 0.75, 0.5)


class ValidationFailure(ValueError):
    def __init__(self, field, message):
        super().__init__(message)
        self.field, self.message = field, message


def _num(req, field, lo, hi, default=None, allow_none=False):
    v = req.get(field, default)
    if v is None:
        if allow_none:
            return None
        raise ValidationFailure(field, f"{field} is required")
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise ValidationFailure(field, f"{field} must be a number")
    if not (lo <= v <= hi):
        raise ValidationFailure(field, f"{field} must be between {lo} and {hi}")
    return v


def _choice(req, field, allowed, default=None):
    v = req.get(field, default)
    if isinstance(v, str):
        v = v.strip().lower()
    if v not in allowed:
        raise ValidationFailure(field, f"{field} must be one of: {', '.join(map(str, allowed))}")
    return v


def validate(req):
    unit = req.get("area_unit", "acre")
    if unit not in ("acre", "sqm"):
        raise ValidationFailure("area_unit", "area_unit must be 'acre' or 'sqm'")
    area_value = _num(req, "area_value", 0.0001, 10_000_000)
    area_acres = area_value if unit == "acre" else area_value / ACRE_M2
    if not (0.1 <= area_acres <= 100):
        raise ValidationFailure("area_value", "Field area must be between 0.1 and 100 acres")

    crop = _choice(req, "crop_id", tuple(engine.CROPS_DB))
    stage_key = req.get("stage_key")
    if stage_key is not None and stage_key not in engine.CROPS_DB[crop]["stages"]:
        raise ValidationFailure("stage_key", f"stage_key must be one of: {', '.join(engine.CROPS_DB[crop]['stages'])}")

    sowing = req.get("sowing_date")
    if sowing:
        try:
            sowing = datetime.strptime(str(sowing)[:10], "%Y-%m-%d").date()
        except ValueError:
            raise ValidationFailure("sowing_date", "sowing_date must look like 2026-09-25")
    elif stage_key is None:
        raise ValidationFailure("sowing_date", "sowing_date (or stage_key) is required")

    feel = _choice(req, "soil_feel", ("auto", *SOIL_FEEL), "auto")
    avail = _num(req, "water_avail_factor", 0.25, 1.0, 1.0)
    if min(abs(avail - a) for a in WATER_AVAIL) > 0.01:
        raise ValidationFailure("water_avail_factor", "water_avail_factor must be 1.0, 0.75 or 0.5")

    return {
        "crop": crop,
        "stage_key": stage_key,
        "sowing": sowing or None,
        "soil": _choice(req, "soil_id", tuple(engine.SOILS_DB)),
        "method": _choice(req, "irrigation_method", METHODS),
        "language": LANGUAGES[_choice(req, "language", tuple(LANGUAGES), "en")],
        "area_acres": area_acres,
        "pump_hp": _num(req, "pump_hp", 0.5, 50, 5.0),
        "pump_lph": _num(req, "pump_discharge_lph", 500, 200_000),
        "lat": _num(req, "latitude", -90, 90),
        "lon": _num(req, "longitude", -180, 180),
        "observed_rain_mm": _num(req, "observed_rain_mm", 0, 300, 0.0),
        "soil_feel": feel,
        "sensor_pct": _num(req, "sensor_moisture_pct", 0, 100, None, allow_none=True),
        "days_since_irrigation": int(_num(req, "days_since_irrigation", 0, 120, 3)),
        "crop_stress": _choice(req, "crop_stress", tuple(CROP_STRESS), "normal"),
        "mulch": _choice(req, "mulch", tuple(MULCH_EVAP_CUT), "none"),
        "power_slot": _choice(req, "power_slot", tuple(POWER_SLOTS), "day"),
        "avail": avail,
        "demo": bool(req.get("use_demo_weather", False)),
        "place": str(req.get("place") or "")[:60],
    }


def pick_stage(crop, das):
    """Growth stage from days after sowing, using Arya's stage lengths.
    Returns (stage_key, stage_dict, past_end)."""
    stages = engine.CROPS_DB[crop]["stages"]
    total = 0
    for key, s in stages.items():
        total += s["stage_duration_days"]
        if das < total:
            return key, s, False
    last = list(stages)[-1]
    return last, stages[last], True


def _effective_rain(mm):
    """Same USDA-SCS rule the engine uses for forecast rain."""
    if mm <= 0:
        return 0.0
    return max(0.0, 0.8 * mm - 5.0) if mm > 25 else max(0.0, 0.6 * mm - 1.0)


def _engine_weather(df, evap_cut):
    """Open-Meteo rows -> the list of dicts plan_week() expects."""
    rows = []
    for r in df.to_dict(orient="records"):
        rain = float(r["rain_mm"])
        prob = r.get("rain_prob_pct")
        if prob is None or pd.isna(prob):
            # No probability in the data: treat forecast rain as certain (documented assumption).
            prob = 100.0 if rain >= 1.0 else 0.0
        row = {"date": str(r["date"]), "temp_max": float(r["tmax_c"]), "rain_mm": rain,
               "rain_prob_pct": float(prob), "et0_mm": float(r["et0_mm"]) * (1.0 - evap_cut)}
        tmin = r.get("tmin_c")
        if tmin is not None and not pd.isna(tmin):
            row["temp_min"] = float(tmin)
        rows.append(row)
    return rows


def build_advice(req, bundle=None, today=None):
    v = validate(req)
    today = today or date.today()

    if bundle is None:
        if v["demo"]:
            df = sample_weather(7)
            bundle = {"df": df, "meta": {
                "source": "sample", "provider": "Built-in DEMO data", "latitude": v["lat"],
                "longitude": v["lon"], "timezone": "local", "retrieved_at": _now_iso(),
                "forecast_start": str(df.date.iloc[0]), "forecast_end": str(df.date.iloc[-1]),
                "note": "DEMO DATA (requested)", "current": {}}}
        else:
            bundle = get_weather_with_meta(v["lat"], v["lon"], 7)
    meta, wdf = bundle["meta"], bundle["df"]

    warnings = []
    # ---- growth stage ----
    if v["stage_key"]:
        stage_key, past_end, das = v["stage_key"], False, None
        stage = engine.CROPS_DB[v["crop"]]["stages"][stage_key]
    else:
        das = (today - v["sowing"]).days
        if das < 0:
            warnings.append("Sowing date is in the future; showing the first growth stage.")
            das = 0
        stage_key, stage, past_end = pick_stage(v["crop"], das)
        if past_end:
            warnings.append("The crop is past its usual season length; showing the last growth stage.")

    # ---- soil moisture (measured, felt, or model estimate) ----
    soil = engine.SOILS_DB[v["soil"]]
    zr = max(0.15, stage["root_depth_m"])
    _, _, _, default_pct = engine.calculate_soil_water_balance(
        soil["field_capacity_pct"], soil["wilting_point_pct"], stage["root_depth_m"],
        stage["depletion_fraction_p"], None)
    if v["sensor_pct"] is not None:
        pct, msrc = v["sensor_pct"], "Sensor reading entered by farmer"
    elif v["soil_feel"] != "auto":
        pct = SOIL_FEEL[v["soil_feel"]]
        msrc = f"Farmer's soil feel test (about {pct:g}%)"
    else:
        pct = default_pct
        msrc = "Model estimate (no sensor or soil feel entered; assumes 60% of the readily available water is used)"
    if v["observed_rain_mm"] > 0:
        pct += _effective_rain(v["observed_rain_mm"]) / (10.0 * zr)   # mm of water -> % moisture
        msrc += f" + {v['observed_rain_mm']:g} mm rain observed on the field"
    pct = round(min(pct, soil["field_capacity_pct"] + 5.0), 1)

    # ---- engine ----
    res = engine.plan_week(
        crop=v["crop"], stage=stage_key, soil_type=v["soil"],
        weather_data=_engine_weather(wdf, MULCH_EVAP_CUT[v["mulch"]]),
        irrigation_method=v["method"], farm_size_acres=v["area_acres"],
        current_soil_moisture_pct=pct, pump_hp=v["pump_hp"], pump_discharge_lph=v["pump_lph"])
    summ, days = res["summary"], res["daily_plan"]
    eff = engine.IRRIGATION_EFFICIENCIES[v["method"]]
    mult = CROP_STRESS[v["crop_stress"]] * v["avail"]

    def day_numbers(d):
        net = round(d["irrigation_mm"] * mult, 1)
        gross = round(net / eff, 1)
        litres = round(gross * ACRE_M2 * v["area_acres"])
        return net, gross, litres

    net_mm, gross_mm, liters = day_numbers(days[0])
    pump_minutes = round(liters / v["pump_lph"] * 60) if gross_mm > 0 else 0
    decision = {"irrigate": "irrigate", "no irrigation": "wait", "check later": "check"}[days[0]["decision"]]

    # ---- confidence: engine's own heuristic, capped when weather is not live ----
    score, label = round(summ["confidence_score"] * 100), summ["confidence"].title()
    conf_reasons = ["Engine heuristic (rain-forecast certainty and soil state); not statistically calibrated."]
    if meta["source"] != "live":
        score, label = min(score, 50), "Low"
        conf_reasons.append("Weather is " + ("an older saved forecast." if meta["source"] == "cached"
                                             else "DEMO data, not a real forecast."))
        warnings.append(meta.get("note") or "Weather is not live.")
    if v["sensor_pct"] is None and v["soil_feel"] == "auto":
        conf_reasons.append("Soil moisture is a model estimate; enter a sensor value or soil feel for a firmer answer.")
    if decision == "wait" and "Rainfall" in days[0]["reason"]:
        warnings.append("Irrigation held because of FORECAST rain, which may not arrive.")

    # ---- weather block for the dashboard ----
    cur = meta.get("current") or {}
    d1 = days[1] if len(days) > 1 else days[0]
    weather = {
        "source": meta["source"], "provider": meta.get("provider"), "retrieved_at": meta.get("retrieved_at"),
        "note": meta.get("note", ""), "forecast_start": meta["forecast_start"], "forecast_end": meta["forecast_end"],
        "temp_c": cur.get("temperature_2m"), "humidity": cur.get("relative_humidity_2m"),
        "wind_kmh": cur.get("wind_speed_10m"),
        "et0_today": round(float(wdf["et0_mm"].iloc[0]), 1), "etc_today": round(days[0]["etc_mm"], 1),
        "rain_48h_mm": round(days[0]["rain_forecast_mm"] + d1["rain_forecast_mm"], 1),
        "rain_prob_max": int(max(days[0]["rain_prob_pct"], d1["rain_prob_pct"])),
    }

    plan = []
    for d in days:
        n, g, litres = day_numbers(d)
        plan.append({"date": str(d["date"]), "decision": d["decision"], "rain_mm": d["rain_forecast_mm"],
                     "rain_prob_pct": d["rain_prob_pct"], "tmax_c": d["temp_max"], "etc_mm": d["etc_mm"],
                     "net_mm": n, "gross_mm": g, "liters": litres, "moisture_pct": d["soil_moisture_pct"],
                     "reason": d["reason"]})

    methods = []
    for m in METHODS:
        e = engine.IRRIGATION_EFFICIENCIES[m]
        g = round(net_mm / e, 1)
        litres = round(g * ACRE_M2 * v["area_acres"])
        mins = round(litres / v["pump_lph"] * 60) if g > 0 else 0
        methods.append({"id": m, "efficiency_pct": int(e * 100), "gross_mm": g, "liters": litres,
                        "minutes": mins, "kwh": round(mins / 60 * v["pump_hp"] * KW_PER_HP, 1)})

    adj = []
    if v["crop_stress"] != "normal":
        adj.append(f"Crop stress '{v['crop_stress']}' scales water by {CROP_STRESS[v['crop_stress']]:g}")
    if v["avail"] < 1:
        adj.append(f"Water availability {v['avail']:g} scales water by {v['avail']:g}")
    if v["mulch"] != "none":
        adj.append(f"Mulch '{v['mulch']}' cuts evaporation by {MULCH_EVAP_CUT[v['mulch']]:.0%}")

    return {
        "decision": decision,
        "net_mm": net_mm, "gross_mm": gross_mm, "liters": liters, "pump_minutes": pump_minutes,
        "best_slot": POWER_SLOTS[v["power_slot"]],
        "reason": days[0]["reason"],
        "confidence": {"score": score, "label": label, "reasons": conf_reasons},
        "weather": weather,
        "stage": {"key": stage_key, "label": stage["stage_display_name"], "das": das, "kc": stage["kc"]},
        "moisture": {"pct": pct, "source": msrc},
        "charts": {"moisture_pct": [d["soil_moisture_pct"] for d in days[:4]],
                   "rain_mm": [d["rain_forecast_mm"] for d in days[:4]],
                   "irrigation_mm": [p["gross_mm"] for p in plan[:4]]},
        "methods": methods,
        "plan": plan,
        "savings": res["savings_vs_fixed"],
        "warnings": warnings,
        "assumptions": [
            f"Method efficiency {int(eff * 100)}% ({v['method']}); gross = net / efficiency",
            "Soil moisture is " + ("the value you entered" if msrc.startswith(("Sensor", "Farmer")) else "a model estimate")
            + ", not a satellite reading",
            "Forecast rain of 10 mm or more with 60% probability holds irrigation",
            "ETc = ET0 x Kc (FAO-56 single crop coefficient)",
            "Savings compare with an assumed fixed 25 mm every 3 days (illustrative)",
            *adj,
        ],
        "inputs_used": {"crop": engine.CROPS_DB[v["crop"]]["crop_name"], "crop_id": v["crop"],
                        "soil": soil["soil_name"], "method": v["method"], "area_acres": v["area_acres"],
                        "pump_hp": v["pump_hp"], "pump_lph": v["pump_lph"],
                        "lat": v["lat"], "lon": v["lon"], "days_since_irrigation": v["days_since_irrigation"]},
        "_language": v["language"],
        "_place": v["place"],
    }
