"""Engine + fallback-text tests (7 cases). Run from the project root:  python run_tests.py
Data-agnostic: moisture values are computed from whatever crops.csv / soils.csv contain."""
import engine
from weather import sample_weather
from ai_explain import fallback

CROP, STAGE, SOIL = "wheat", "initial", "loam"


def day(rain=0.0, prob=10, tmax=34.0, et0=5.0):
    return {"temp_max": tmax, "rain_mm": rain, "rain_prob_pct": prob, "et0_mm": et0}


def week(first=None, second=None):
    days = [day() for _ in range(7)]
    if first:
        days[0] = first
    if second:
        days[1] = second
    return days


def params():
    c = engine.get_crop_stage_params(CROP, STAGE)
    s = engine.get_soil_params(SOIL)
    zr = max(0.15, c["root_depth_m"])
    taw, raw, _, _ = engine.calculate_soil_water_balance(
        s["field_capacity_pct"], s["wilting_point_pct"], c["root_depth_m"], c["depletion_fraction_p"], None)
    return s, zr, taw, raw


def moisture_for_depletion(dep_mm):
    s, zr, _, _ = params()
    return s["field_capacity_pct"] - dep_mm / (10.0 * zr)


def today(weather, moisture_pct, method="drip", acres=1.0, pump_lph=15000.0):
    r = engine.plan_week(CROP, STAGE, SOIL, weather, method, acres, moisture_pct, pump_discharge_lph=pump_lph)
    return r["summary"], r


def check_multilingual():
    r = {"irrigate_mm": 10.0, "litres": 40000.0, "minutes": 160.0, "reason": "Soil moisture adequate.",
         "decision": "irrigate"}
    en, hi, mr = fallback(r, "English"), fallback(r, "Hindi"), fallback(r, "Marathi")
    return "litres" in en and "लीटर" in hi and "लिटर" in mr


def check_math_precision():
    # 10 mm gross * 1 acre = 40468.6 L; at 15000 L/h that is 161.87 min. Engine rounds minutes.
    s, zr, taw, raw = params()
    res = engine.plan_week(CROP, STAGE, SOIL, week(), "drip", 1.0, s["wilting_point_pct"], pump_discharge_lph=15000.0)
    d = res["daily_plan"][0]
    litres = d["gross_irrigation_mm"] * 4046.86
    return d["decision"] == "irrigate" and abs(d["pump_minutes"] - round(litres / 15000.0 * 60)) <= 1


_, _, TAW, RAW = params()
tests = [
    ("TC-01: Dry soil (at wilting point), no rain -> Irrigate",
     lambda: today(week(), params()[0]["wilting_point_pct"])[0]["today_decision"] == "irrigate"),
    ("TC-02: Rain 18 mm, 78% probability tomorrow, soil not dead dry -> Hold",
     lambda: today(week(second=day(18.0, 78)), moisture_for_depletion(RAW * 1.05))[0]["today_decision"] == "no irrigation"),
    ("TC-03: Soil at field capacity -> No irrigation",
     lambda: today(week(), params()[0]["field_capacity_pct"])[0]["today_decision"] == "no irrigation"),
    ("TC-04: Savings vs fixed schedule is positive on a rainy week",
     lambda: today(week(first=day(0.0, 20), second=day(18.0, 78)), params()[0]["field_capacity_pct"])[1]["savings_vs_fixed"]["water_savings_pct"] > 0),
    ("TC-05: Weather API failure -> Offline sample fallback",
     lambda: len(sample_weather(7)) == 7 and "date" in sample_weather(7).columns),
    ("TC-06: Multilingual fallback generation (EN/HI/MR)", check_multilingual),
    ("TC-07: Volume and pump duration math precision", check_math_precision),
]

all_passed = True
for name, check in tests:
    result = bool(check())
    all_passed &= result
    print("PASS" if result else "FAIL", "-", name)
print("\nAll 7 test cases passed successfully." if all_passed else "\nSome test cases failed.")
raise SystemExit(0 if all_passed else 1)
