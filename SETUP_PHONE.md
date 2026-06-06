# Endurance Coach — Automated Performance & Nutrition Dashboard

Pulls your **WHOOP** recovery / HRV / sleep / strain and **TrainingPeaks**
workouts, computes your **TDEE, macros, hydration, and CTL/ATL/TSB**, asks
**OpenAI** to write a daily coaching brief, and writes everything to a
**Google Sheet** that becomes your dashboard's data source.

It runs in **DRY-RUN mode out of the box** (realistic mock data, no keys
needed) so you can see the full pipeline immediately, then flip on real APIs
one at a time.

```
WHOOP ─┐
       ├─► compute TDEE · macros · hydration · PMC ─► OpenAI brief ─► Google Sheet
TrainingPeaks ─┘                                                          ▲
                                                                    your dashboard
```

## Quick start (no keys, 60 seconds)

```bash
pip install -r requirements.txt
cp .env.example .env          # DRY_RUN=true is already set
python main.py                # today
python main.py --backfill 14  # last 14 days, builds a CTL/ATL/TSB trend
```

You'll get a printed briefing for each day and a preview of the row that would
be written to your sheet. When you're ready, connect the real services below
and set `DRY_RUN=false`.

## Your profile

Edit these in `.env` — they drive the TDEE / macro / hydration math:

`ATHLETE_NAME, SEX, AGE, HEIGHT_CM, WEIGHT_KG, BODYFAT_PCT (optional), GOAL`

`GOAL` is one of `performance | fatloss | maintenance | muscle` and shifts your
calorie and macro targets.

## Connect WHOOP

1. Create a developer app at <https://developer.whoop.com> (Apps → Create).
2. Set the redirect URI to `http://localhost:8080/callback`.
3. Put `WHOOP_CLIENT_ID` and `WHOOP_CLIENT_SECRET` in `.env`.
4. Authorise once — this opens a browser and prints a refresh token:

   ```bash
   python -m clients.whoop
   ```

5. Paste the printed `WHOOP_REFRESH_TOKEN=...` into `.env`.

The refresh token auto-rotates and is cached, so this is a one-time step.

## Connect TrainingPeaks (optional)

TrainingPeaks has **no self-serve public API** — access requires partner
approval. If you don't have it, **leave `TRAININGPEAKS_TOKEN` blank**: the app
derives a Training Stress Score from your WHOOP workout strain, so
**CTL/ATL/TSB still work**. If you do get credentials, set `TRAININGPEAKS_TOKEN`
and `TRAININGPEAKS_ATHLETE_ID` and the real workouts/TSS are used automatically.

> **What CTL/ATL/TSB mean** — CTL ("fitness") is a 42-day average of training
> stress, ATL ("fatigue") a 7-day average, and TSB ("form") = yesterday's
> CTL − ATL. This is the Performance Management Chart serious coaches use to
> time peaks and avoid overtraining.

## Connect Google Sheets

1. In Google Cloud Console: create a project → enable the **Google Sheets API**.
2. Create a **Service Account** → add a **JSON key** → download it as
   `service_account.json` next to `main.py`.
3. Create a spreadsheet named exactly what you set in `GOOGLE_SHEET_NAME`
   (default `Endurance Coach`).
4. **Share that spreadsheet** with the service account's email
   (`...@...iam.gserviceaccount.com`) as **Editor**.

The app creates a `Daily` worksheet with headers on first run. Build any chart
or dashboard on top of that sheet — or point Looker Studio / your existing web
app at it.

## Connect OpenAI

Put `OPENAI_API_KEY` in `.env`. Default model is `gpt-4o-mini` (cheap); change
`OPENAI_MODEL` if you like. Without a key, a solid rules-based briefing is used.

## Go live

```bash
# in .env
DRY_RUN=false
```

```bash
python main.py
```

## Run it every day

Built-in scheduler (keep the process running):

```bash
python scheduler.py     # runs now, then daily at 07:00
```

Or use the OS scheduler:

```cron
# crontab -e  — every day at 7am
0 7 * * * cd /path/to/endurance-coach && /usr/bin/python3 main.py >> coach.log 2>&1
```

For an always-on cloud setup, deploy the folder to **Render** or **Railway** as
a Cron Job (command `python main.py`), with the `.env` values set as
environment variables and `service_account.json` added as a secret file.

## Put it on your phone (PWA)

You get a real **home-screen app** on your iPhone — its own icon, full-screen,
works offline — without the App Store. It's a Progressive Web App served by the
small Flask app in `web/`, reading the same Google Sheet the daily job fills.

```
[Render cron: main.py] ──writes──► Google Sheet ──reads──► [Render web: web/app.py] ──► PWA on your phone
        daily 07:00                  (your DB)                    /api/data
```

### Preview it locally first (no keys)

```bash
pip install -r requirements.txt
python web/app.py            # DRY_RUN=true -> mock data
# open http://localhost:8000 in your browser
```

On a phone on the same Wi-Fi, open `http://<your-computer-ip>:8000`.

### Deploy to Render (free) — one blueprint, two services

The included `render.yaml` creates **both** the daily cron job and the web app.

1. Push this folder to a GitHub repo.
2. Render → **New → Blueprint** → pick the repo. It reads `render.yaml` and
   creates `endurance-coach-pwa` (web) + `endurance-coach-daily` (cron).
3. Add your secrets as environment variables on **both** service