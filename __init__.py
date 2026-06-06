"""Deterministic mock data so the whole pipeline runs without any API keys."""
import datetime as dt
import random


def mock_whoop_day(day: dt.date) -> dict:
    random.seed(day.toordinal())
    strain = round(random.uniform(8, 17), 1)
    cals = round(random.uniform(400, 1100))
    return {
        "date": day.isoformat(),
        "recovery_pct": random.randint(35, 95),
        "hrv_ms": random.randint(45, 110),
        "resting_hr": random.randint(44, 58),
        "strain": strain,
        "kilojoules": round(cals * 4.184),
        "calories_burned": cals,
        "sleep_performance_pct": random.randint(60, 98),
        "sleep_hours": round(random.uniform(5.5, 8.5), 1),
        "sleep_debt_hours": round(random.uniform(0, 2.5), 1),
        "respiratory_rate": round(random.uniform(13, 16), 1),
        "workouts": [{
            "sport": random.choice(["Running", "Cycling", "Strength"]),
            "strain": strain,
            "calories": cals,
            "avg_hr": random.randint(120, 150),
            "max_hr": random.randint(160, 185),
            "distance_m": random.choice([None, 8000, 12000, 21000]),
            "duration_min": random.randint(40, 110),
        }],
    }
