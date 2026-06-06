"""Central configuration, loaded from environment / .env file."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _f(key, default=None):
    v = os.getenv(key, "")
    return float(v) if v.strip() else default


def _b(key, default=False):
    return os.getenv(key, str(default)).strip().lower() in ("1", "true", "yes")


@dataclass
class Athlete:
    name: str = os.getenv("ATHLETE_NAME", "Athlete")
    sex: str = os.getenv("SEX", "male").lower()
    age: int = int(_f("AGE", 35))
    height_cm: float = _f("HEIGHT_CM", 178)
    weight_kg: float = _f("WEIGHT_KG", 75)
    bodyfat_pct: float = _f("BODYFAT_PCT")          # may be None
    goal: str = os.getenv("GOAL", "performance").lower()


class Config:
    DRY_RUN = _b("DRY_RUN", True)
    athlete = Athlete()

    WHOOP_CLIENT_ID = os.getenv("WHOOP_CLIENT_ID", "")
    WHOOP_CLIENT_SECRET = os.getenv("WHOOP_CLIENT_SECRET", "")
    WHOOP_REDIRECT_URI = os.getenv("WHOOP_REDIRECT_URI", "http://localhost:8080/callback")
    WHOOP_REFRESH_TOKEN = os.getenv("WHOOP_REFRESH_TOKEN", "")

    TP_TOKEN = os.getenv("TRAININGPEAKS_TOKEN", "")
    TP_ATHLETE_ID = os.getenv("TRAININGPEAKS_ATHLETE_ID", "")

    GOOGLE_SA_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
    GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Endurance Coach")

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


config = Config()
