# Get the app on your phone — step by step

No coding needed. We do it in two stages:

- **Stage 1** puts the app on your phone today, showing a **demo dashboard** —
  needs only two free accounts, no API keys. ~15 minutes.
- **Stage 2** swaps the demo data for **your real WHOOP + nutrition data**.
  Do this whenever you're ready.

Take it one numbered step at a time. Each step says what you'll see.

---

## Stage 1 — App on your phone (demo data)

You'll create two free accounts: **GitHub** (stores the code) and **Render**
(runs it on the internet). No credit card required.

### 1. Make a GitHub account
1. Go to <https://github.com> and click **Sign up**.
2. Enter an email, password, username. Verify your email.

### 2. Put the project on GitHub (drag-and-drop, no commands)
1. Once logged in, click the **+** at the top-right → **New repository**.
2. Name it `endurance-coach`. Leave everything else as-is. Click
   **Create repository**.
3. On the next page, click the link **"uploading an existing file"**
   (it's in the line: *"…or push an existing repository…"* — look just above it
   for **"uploading an existing file"**).
4. Open the `endurance-coach` folder on your computer. Select **all** the files
   and folders inside it, and **drag them onto the GitHub page**.
   - Tip: drag the *contents* (main.py, web, clients, render.yaml, …), not the
     outer folder.
5. Scroll down, click **Commit changes**. Wait for the files to appear.

### 3. Make a Render account
1. Go to <https://render.com> → **Get Started**.
2. Choose **Sign in with GitHub** (easiest — it links the two automatically)
   and approve access.

### 4. Deploy the app
1. In Render, click **New +** (top right) → **Blueprint**.
2. Pick your `endurance-coach` repository from the list → **Connect**.
3. Render reads the included `render.yaml` and shows two services
   (`endurance-coach-pwa` and `endurance-coach-daily`). You don't need to change
   anything for the demo. Click **Apply** / **Create Resources**.
4. Wait 2–4 minutes while it builds (you'll see logs scroll, then "Live").

### 5. Open your app
1. Click the `endurance-coach-pwa` service. Near the top is its URL, like
   `https://endurance-coach-pwa.onrender.com`. Click it.
2. You should see the dashboard (with demo numbers). 🎉
   - First open after idle can take ~30s to wake up — that's normal on the
     free plan.

### 6. Add it to your iPhone home screen
1. Open that same URL in **Safari** on your iPhone (must be Safari).
2. Tap the **Share** button (the square with an upward arrow, bottom center).
3. Scroll down and tap **Add to Home Screen** → **Add** (top right).
4. You now have a **Coach** icon on your home screen. Open it — full screen, no
   browser bars.

**Android:** open the URL in Chrome → tap **⋮** menu → **Install app** /
**Add to Home screen**.

✅ Done with Stage 1. The app is on your phone. It just shows sample data for
now — Stage 2 makes it yours.

---

## Stage 2 — Switch to your real data

This connects WHOOP, a Google Sheet, and the AI coach. It's more involved
(each service needs a key). Full details for each are in **README.md** — here's
the order and where to paste things.

1. **Get your keys** (see README sections "Connect WHOOP", "Connect Google
   Sheets", "Connect OpenAI"):
   - WHOOP: `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`, and a
     `WHOOP_REFRESH_TOKEN` (the README's one-time authorise step prints it).
   - Google: a `service_account.json` file, and share your sheet with its email.
   - OpenAI: an `OPENAI_API_KEY`.

2. **Tell Render to use live data.** In each of the two Render services →
   **Environment** tab:
   - Change `DRY_RUN` from `true` to `false`.
   - Add your secrets: `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`,
     `WHOOP_REFRESH_TOKEN`, `OPENAI_API_KEY`.
   - Update the profile values (`WEIGHT_KG`, `AGE`, `GOAL`, …) to your real
     numbers.

3. **Add the Google key file.** In each service → **Secret Files** → add a file
   named `service_account.json`, paste in the contents of your downloaded key.

4. **Save.** Render redeploys automatically. The daily job
   (`endurance-coach-daily`) now writes your real metrics to the sheet every
   morning, and your phone app reads them.

That's it — same icon on your phone, now powered by your own WHOOP recovery,
training load, and AI nutrition targets.

---

### If something looks off
- **App is blank / "no data yet":** the daily job hasn't run yet. In Render,
  open `endurance-coach-daily` → **Manual Run** once to populate immediately.
- **Slow first load:** free Render services sleep when idle; give it ~30s.
- **Want a morning notification** of the brief (Telegram/email) instead of
  opening the app? Ask and I'll add it.
