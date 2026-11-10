"""TerraFlow API. Run:  python -m uvicorn server:app --reload
Serves ./frontend (the website) and /api/* from ONE origin, so no CORS setup is needed.

Numbers always come from the engine (service.build_advice). Nugen AI writes the
farmer-facing language around them (see ai_explain.py)."""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import ai_explain
import service
from weather import get_weather_with_meta


@asynccontextmanager
async def lifespan(_app):
    # Nugen is a REQUIRED part of the product. Set NUGEN_REQUIRED=0 in .env only
    # for local development without a key.
    if ai_explain.REQUIRED and not ai_explain.configured():
        raise RuntimeError(
            "Nugen AI is required but not configured. Put NUGEN_API_KEY, NUGEN_API_URL and "
            "NUGEN_MODEL in .env (see .env.example), or set NUGEN_REQUIRED=0 for local development.")
    if not ai_explain.configured():
        print("WARNING: Nugen AI is not configured; built-in fallback text will be shown.")
    yield


app = FastAPI(title="TerraFlow API", version="0.3.0", lifespan=lifespan)
FRONTEND = Path(__file__).resolve().parent / "frontend"


class AdviceRequest(BaseModel):
    """Same fields the website sends (see buildRequest() in frontend/index.html)."""
    crop_id: str
    soil_id: str
    irrigation_method: str
    area_value: float
    area_unit: str = "acre"
    pump_hp: float = 5.0
    pump_discharge_lph: float
    latitude: float
    longitude: float
    language: str = "en"                       # en | mr | hi
    sowing_date: Optional[str] = None          # YYYY-MM-DD
    stage_key: Optional[str] = None            # alternative to sowing_date
    observed_rain_mm: float = 0.0
    soil_feel: str = "auto"
    sensor_moisture_pct: Optional[float] = None
    days_since_irrigation: int = 3
    crop_stress: str = "normal"
    mulch: str = "none"
    power_slot: str = "day"
    water_avail_factor: float = 1.0
    use_demo_weather: bool = False
    with_ai: bool = False
    place: str = ""


class AskRequest(AdviceRequest):
    question: str = ""


@app.exception_handler(service.ValidationFailure)
def _validation(_, exc: service.ValidationFailure):
    return JSONResponse(status_code=422, content={"field": exc.field, "message": exc.message})


def _public(result):
    return {k: v for k, v in result.items() if not k.startswith("_")}


@app.get("/api/health")
def health():
    return {"status": "ok", "version": app.version}


@app.get("/api/ai/status")
def ai_status(ping: bool = False):
    """For the 'Nugen AI connected' pill. ?ping=true makes one real test call."""
    out = ai_explain.status()
    if ping:
        out["ping"] = ai_explain.ping()
    return out


@app.get("/api/weather")
def weather(lat: float, lon: float):
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise service.ValidationFailure("lat/lon", "Coordinates out of range")
    b = get_weather_with_meta(lat, lon, 7)
    df = b["df"].astype(object).where(b["df"].notna(), None)   # NaN is not valid JSON
    return {"meta": b["meta"], "daily": df.to_dict(orient="records")}


@app.post("/api/advice")
def advice(req: AdviceRequest):
    """Engine numbers. With with_ai=true, Nugen also writes the explanation."""
    a = service.build_advice(req.model_dump())
    out = _public(a)
    if req.with_ai:
        out["ai"] = {"explanation": ai_explain.web_view(ai_explain.explain_with_meta(a, a["_language"]))}
    return out


@app.post("/api/explain")
def explain(req: AdviceRequest):
    a = service.build_advice(req.model_dump())
    return ai_explain.web_view(ai_explain.explain_with_meta(a, a["_language"]))


@app.post("/api/summary")
def summary(req: AdviceRequest):
    a = service.build_advice(req.model_dump())
    return ai_explain.web_view(ai_explain.weekly_outlook(a, a["_language"]))


@app.post("/api/ask")
def ask(req: AskRequest):
    a = service.build_advice(req.model_dump())
    return ai_explain.web_view(ai_explain.ask(req.question, a, a["_language"]))


@app.post("/api/share")
def share(req: AdviceRequest):
    a = service.build_advice(req.model_dump())
    return ai_explain.web_view(ai_explain.share_message(a, a["_language"], a["_place"]))


if FRONTEND.exists():  # mounted last so /api/* wins
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
