# ──────────────────────────────────────────────────────────────
# Endurance Coach — environment configuration
# Copy this file to ".env" and fill in your values.
# ──────────────────────────────────────────────────────────────

# Run without real APIs (uses built-in mock data). "true" or "false".
DRY_RUN=true

# ---- Athlete profile (used for TDEE / macro / hydration math) ----
ATHLETE_NAME=Osho
SEX=male                 # male | female
AGE=35
HEIGHT_CM=180
WEIGHT_KG=75
BODYFAT_PCT=15           # optional; improves TDEE estimate. blank = ignored
GOAL=performance         # performance | fatloss | maintenance | muscle

# ---- WHOOP (https://developer.whoop.com) ----
WHOOP_CLIENT_ID=
WHOOP_CLIENT_SECRET=
WHOOP_REDIRECT_URI=http://localhost:8080/callback
# Filled automatically by `python -m clients.whoop` (the auth helper):
WHOOP_REFRESH_TOKEN=

# ---- TrainingPeaks ----
# TP's public API requires partner approval. If you don't have it,
# leave blank — the app falls back to WHOOP workouts automatically.
TRAININGPEAKS_TOKEN=
TRAININGPEAKS_ATHLETE_ID=

# ---- Google Sheets ----
# Path to a Google service-account JSON key file.
GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json
# The spreadsheet name (must be shared with the service-account email).
GOOGLE_SHEET_NAME=Endurance Coach

# ---- OpenAI ----
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
