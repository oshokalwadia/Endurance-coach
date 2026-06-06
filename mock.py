"""Sports-science math: TDEE, macros, hydration."""
from config import Athlete


def bmr(a: Athlete) -> float:
    """Resting metabolic rate. Uses Katch-McArdle if bodyfat known, else Mifflin."""
    if a.bodyfat_pct:
        lean = a.weight_kg * (1 - a.bodyfat_pct / 100)
        return 370 + 21.6 * lean
    s = 5 if a.sex == "male" else -161
    return 10 * a.weight_kg + 6.25 * a.height_cm - 5 * a.age + s


def tdee(a: Athlete, calories_burned: float | None, base_activity: float = 1.4) -> float:
    """
    Total daily energy expenditure.

    BMR * a light non-exercise activity factor, PLUS the day's actual
    exercise burn measured by WHOOP (so hard days automatically eat more).
    """
    resting = bmr(a) * base_activity
    exercise = calories_burned or 0
    # WHOOP's kJ-derived burn already includes some resting overlap; net it lightly.
    return round(resting + exercise * 0.85)


def macros(a: Athlete, tdee_kcal: float, strain: float | None, recovery_pct: float | None) -> dict:
    """
    Macro split tuned to goal, training load, and recovery.

    - Protein scales with bodyweight (1.6–2.2 g/kg).
    - Carbs scale UP on high-strain days and when recovery is low (refuel).
    - Fat fills the remainder with a floor for hormonal health.
    """
    goal = a.goal
    cal = tdee_kcal
    if goal == "fatloss":
        cal = round(tdee_kcal * 0.85)
    elif goal == "muscle":
        cal = round(tdee_kcal * 1.08)

    protein_g_per_kg = {"fatloss": 2.2, "muscle": 2.0, "performance": 1.8, "maintenance": 1.6}.get(goal, 1.8)
    protein_g = round(a.weight_kg * protein_g_per_kg)

    hard = (strain or 0) >= 12 or (recovery_pct is not None and recovery_pct < 50)
    carb_g_per_kg = 7.0 if hard else 4.5
    if goal == "fatloss":
        carb_g_per_kg = 5.0 if hard else 2.5
    carb_g = round(a.weight_kg * carb_g_per_kg)

    kcal_pf = protein_g * 4 + carb_g * 4
    fat_g = max(round(a.weight_kg * 0.8), round((cal - kcal_pf) / 9))

    return {
        "calories": cal,
        "protein_g": protein_g,
        "carbs_g": carb_g,
        "fat_g": fat_g,
        "refuel_day": hard,
    }


def hydration(a: Athlete, calories_burned: float | None, strain: float | None) -> dict:
    """Daily fluid + sodium targets."""
    base_ml = a.weight_kg * 33                       # ~33 ml/kg baseline
    sweat_ml = (calories_burned or 0) * 1.0          # rough: ~1 ml per kcal of exercise
    total_ml = round(base_ml + sweat_ml)
    # Sodium: more on hard/sweaty days.
    sodium_mg = 2000 + round((sweat_ml / 1000) * 800)
    return {
        "water_ml": total_ml,
        "water_l": round(total_ml / 1000, 1),
        "sodium_mg": sodium_mg,
        "electrolytes_note": (
            "Add an electrolyte tab/LMNT to ~1L of today's water"
            if (strain or 0) >= 12 else "Normal electrolyte intake is fine today"
        ),
    }
