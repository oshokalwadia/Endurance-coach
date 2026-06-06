# One-click deploy: Render reads this file and creates both services.
# Ships in DEMO mode (DRY_RUN=true) so the FIRST deploy needs no keys.
# To go live with real data: change both DRY_RUN values to "false" and fill
# the sync:false secrets in the Render dashboard. See SETUP_PHONE.md (Stage 2).
services:
  - type: web
    name: endurance-coach-pwa
    runtime: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn web.app:app
    envVars:
      - key: DRY_RUN
        value: "true"
      - key: ATHLETE_NAME
        value: Osho
      - key: SEX
        value: male
      - key: AGE
        value: "35"
      - key: HEIGHT_CM
        value: "180"
      - key: WEIGHT_KG
        value: "75"
      - key: GOAL
        value: performance
      - key: GOOGLE_SHEET_NAME
        value: Endurance Coach
      - key: GOOGLE_SERVICE_ACCOUNT_FILE
        value: /etc/secrets/service_account.json
      - key: WHOOP_CLIENT_ID
        sync: false
      - key: WHOOP_CLIENT_SECRET
        sync: false
      - key: WHOOP_REFRESH_TOKEN
        sync: false
      - key: OPENAI_API_KEY
        sync: false

  - type: cron
    name: endurance-coach-daily
    runtime: python
    plan: free
    schedule: "0 7 * * *"          # 07:00 UTC daily
    buildCommand: pip install -r requirements.txt
    startCommand: python main.py
    envVars:
      - key: DRY_RUN
        value: "true"
      - key: ATHLETE_NAME
        value: Osho
      - key: SEX
        value: male
      - key: AGE
        value: "35"
      - key: HEIGHT_CM
        value: "180"
      - key: WEIGHT_KG
        value: "75"
      - key: GOAL
        value: performance
      - key: GOOGLE_SHEET_NAME
        value: Endurance Coach
      - key: GOOGLE_SERVICE_ACCOUNT_FILE
        value: /etc/secrets/service_account.json
      - key: WHOOP_CLIENT_ID
        sync: false
      -