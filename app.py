"""
Endurance Coach - single-file web app (WHOOP-enabled).

Capabilities activate when their env vars are present (set in Render):
  OPENAI_API_KEY                 -> daily brief written by OpenAI
  WHOOP_CLIENT_ID / _SECRET      -> connect WHOOP for REAL data
  UPSTASH_REDIS_REST_URL / _TOKEN-> remembers your WHOOP login between naps
With no WHOOP/Upstash set, it serves realistic demo data.

Connect WHOOP by visiting:  /whoop/login   (one tap, one time)
Debug helpers:  /whoop/status   /diag
Deploy:  gunicorn app:app --bind 0.0.0.0:$PORT
"""
import os, json, time, random, datetime as dt, base64
import urllib.request, urllib.error, urllib.parse
from flask import Flask, jsonify, request, Response, redirect

app = Flask(__name__)
ATHLETE=os.environ.get("ATHLETE_NAME","Osho"); SEX=os.environ.get("SEX","male")
AGE=int(os.environ.get("AGE","35")); HEIGHT=float(os.environ.get("HEIGHT_CM","180"))
WEIGHT=float(os.environ.get("WEIGHT_KG","75")); GOAL=os.environ.get("GOAL","performance")
OPENAI_KEY=os.environ.get("OPENAI_API_KEY",""); OPENAI_MODEL=os.environ.get("OPENAI_MODEL","gpt-4o-mini")

WHOOP_ID=os.environ.get("WHOOP_CLIENT_ID",""); WHOOP_SECRET=os.environ.get("WHOOP_CLIENT_SECRET","")
WHOOP_REDIRECT=os.environ.get("WHOOP_REDIRECT_URI","https://endure-taq2.onrender.com/whoop/callback")
WHOOP_SCOPES="read:recovery read:cycles read:sleep read:workout offline"
WHOOP_AUTH="https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN="https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_API="https://api.prod.whoop.com/developer/v2"

UPSTASH_URL=os.environ.get("UPSTASH_REDIS_REST_URL",""); UPSTASH_TOKEN=os.environ.get("UPSTASH_REDIS_REST_TOKEN","")
_brief_cache={}; _last_error=None; _mem={}

# ---------------- tiny persistent store (Upstash REST, falls back to memory) ----------------
def kv_get(key):
    if not (UPSTASH_URL and UPSTASH_TOKEN): return _mem.get(key)
    try:
        req=urllib.request.Request(UPSTASH_URL.rstrip("/"),
            data=json.dumps(["GET",key]).encode(),
            headers={"Authorization":f"Bearer {UPSTASH_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req,timeout=15) as r:
            return json.loads(r.read()).get("result")
    except Exception:
        return _mem.get(key)
def kv_set(key,val):
    _mem[key]=val
    if not (UPSTASH_URL and UPSTASH_TOKEN): return
    try:
        req=urllib.request.Request(UPSTASH_URL.rstrip("/"),
            data=json.dumps(["SET",key,val]).encode(),
            headers={"Authorization":f"Bearer {UPSTASH_TOKEN}","Content-Type":"application/json"})
        urllib.request.urlopen(req,timeout=15).read()
    except Exception:
        pass

# ---------------- WHOOP OAuth + data ----------------
def whoop_configured(): return bool(WHOOP_ID and WHOOP_SECRET)

def whoop_exchange(code):
    data=urllib.parse.urlencode({"grant_type":"authorization_code","code":code,
        "client_id":WHOOP_ID,"client_secret":WHOOP_SECRET,"redirect_uri":WHOOP_REDIRECT}).encode()
    return _whoop_token_request(data)
def whoop_refresh(refresh_token):
    if not refresh_token: return None
    data=urllib.parse.urlencode({"grant_type":"refresh_token","refresh_token":refresh_token,
        "client_id":WHOOP_ID,"client_secret":WHOOP_SECRET,"scope":"offline"}).encode()
    return _whoop_token_request(data)
def _whoop_token_request(data):
    global _last_error
    req=urllib.request.Request(WHOOP_TOKEN,data=data,
        headers={"Content-Type":"application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            tok=json.loads(r.read())
        tok["expires_at"]=time.time()+int(tok.get("expires_in",3600))
        return tok
    except urllib.error.HTTPError as e:
        _last_error=f"token HTTP {e.code}: {e.read().decode()[:300]}"; return None
    except Exception as e:
        _last_error=f"token {type(e).__name__}: {e}"; return None

def whoop_access_token():
    raw=kv_get("whoop:token")
    if not raw: return None
    try: blob=json.loads(raw)
    except Exception: return None
    if blob.get("expires_at",0) > time.time()+60:
        return blob.get("access_token")
    new=whoop_refresh(blob.get("refresh_token"))
    if not new: return None
    kv_set("whoop:token",json.dumps(new))
    return new.get("access_token")

def whoop_connected(): return bool(kv_get("whoop:token"))

def _iso(d): return d.isoformat()+"T00:00:00.000Z"
def whoop_collection(path, token, start, end, limit=25):
    global _last_error
    q=urllib.parse.urlencode({"start":start,"end":end,"limit":limit})
    req=urllib.request.Request(f"{WHOOP_API}{path}?{q}",headers={"Authorization":f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            return json.loads(r.read()).get("records",[])
    except urllib.error.HTTPError as e:
        _last_error=f"{path} HTTP {e.code}: {e.read().decode()[:200]}"; return []
    except Exception as e:
        _last_error=f"{path} {type(e).__name__}: {e}"; return []

def _sleep_hours(stage):
    keys=("total_light_sleep_time_milli","total_slow_wave_sleep_time_milli","total_rem_sleep_time_milli")
    vals=[stage.get(k) for k in keys if stage.get(k) is not None]
    return round(sum(vals)/3600000,1) if vals else None
def _sleep_debt(score, hrs):
    need=score.get("sleep_needed") or {}
    tot=sum(v for v in [need.get("baseline_milli"),need.get("need_from_sleep_debt_milli"),
        need.get("need_from_recent_strain_milli"),need.get("need_from_recent_nap_milli")] if isinstance(v,(int,float)))
    if tot and hrs is not None:
        return round(max(0,tot/3600000-hrs),1)
    return None

def build_recent_live(n=14):
    tok=whoop_access_token()
    if not tok: return None
    today=dt.date.today(); start_d=today-dt.timedelta(days=n)
    start=_iso(start_d); end=_iso(today+dt.timedelta(days=1))
    rec=whoop_collection("/recovery",tok,start,end)
    cyc=whoop_collection("/cycle",tok,start,end)
    slp=whoop_collection("/activity/sleep",tok,start,end)
    wko=whoop_collection("/activity/workout",tok,start,end)
    by={}
    for r in rec:
        d=(r.get("created_at") or "")[:10]
        if d: by.setdefault(d,{})["rec"]=r.get("score") or {}
    for c in cyc:
        d=(c.get("start") or "")[:10]
        if d: by.setdefault(d,{})["cyc"]=c.get("score") or {}
    for s in slp:
        d=(s.get("end") or s.get("start") or "")[:10]
        if d and not (s.get("nap")): by.setdefault(d,{})["slp"]=s.get("score") or {}
    for w in wko:
        d=(w.get("start") or "")[:10]
        if d: by.setdefault(d,{}).setdefault("wko",[]).append(w.get("score") or {})
    dates=sorted(by.keys())
    if not dates: return None
    rows=[]; ctl=atl=0.0
    for ds in dates:
        b=by[ds]; rc=b.get("rec",{}); cy=b.get("cyc",{}); sl=b.get("slp",{})
        kj=cy.get("kilojoule"); cals=round(kj/4.184) if kj else None
        strain=cy.get("strain"); dur=None
        hrs=_sleep_hours(sl.get("stage_summary",{}) if sl else {})
        tss=tss_from_strain(strain or 0,dur)
        nc=ctl+(tss-ctl)/42.0; na=atl+(tss-atl)/7.0; tsb=ctl-atl
        td=tdee(cals); rec_pct=rc.get("recovery_score")
        m=macros(td,strain or 0,rec_pct); h=hydration(cals,strain or 0)
        rows.append({"date":ds,"recovery_pct":rec_pct,
            "hrv_ms":round(rc.get("hrv_rmssd_milli")) if rc.get("hrv_rmssd_milli") else None,
            "resting_hr":rc.get("resting_heart_rate"),"strain":round(strain,1) if strain else None,
            "calories_burned":cals,"tdee":td,"sleep_hours":hrs,
            "sleep_performance_pct":sl.get("sleep_performance_percentage"),
            "sleep_debt_hours":_sleep_debt(sl,hrs),
            "respiratory_rate":round(sl.get("respiratory_rate"),1) if sl.get("respiratory_rate") else None,
            "tss":tss,"ctl":round(nc,1),"atl":round(na,1),"tsb":round(tsb,1),
            "cal_target":m["calories"],"protein_g":m["protein_g"],"carbs_g":m["carbs_g"],"fat_g":m["fat_g"],
            "water_l":h["water_l"],"sodium_mg":h["sodium_mg"],
            "recommendation":coach_template(rec_pct or 0,tsb,m,h,_sleep_debt(sl,hrs) or 0)})
        ctl,atl=nc,na
    return rows[-n:]

# ---------------- demo data + sports math ----------------
def mock_day(day):
    random.seed(day.toordinal())
    strain=round(random.uniform(8,17),1); cals=round(random.uniform(400,1100))
    return {"date":day.isoformat(),"recovery_pct":random.randint(35,95),"hrv_ms":random.randint(45,110),
        "resting_hr":random.randint(44,58),"strain":strain,"calories_burned":cals,
        "sleep_performance_pct":random.randint(60,98),"sleep_hours":round(random.uniform(5.5,8.5),1),
        "sleep_debt_hours":round(random.uniform(0,2.5),1),"respiratory_rate":round(random.uniform(13,16),1),
        "duration_min":random.randint(40,110)}
def bmr():
    s=5 if SEX=="male" else -161
    return 10*WEIGHT+6.25*HEIGHT-5*AGE+s
def tdee(c): return round(bmr()*1.4+(c or 0)*0.85)
def macros(td,strain,rec):
    cal=td
    if GOAL=="fatloss": cal=round(td*0.85)
    elif GOAL=="muscle": cal=round(td*1.08)
    ppk={"fatloss":2.2,"muscle":2.0,"performance":1.8,"maintenance":1.6}.get(GOAL,1.8)
    protein=round(WEIGHT*ppk); hard=strain>=12 or (rec is not None and rec<50)
    cpk=7.0 if hard else 4.5
    if GOAL=="fatloss": cpk=5.0 if hard else 2.5
    carb=round(WEIGHT*cpk); fat=max(round(WEIGHT*0.8),round((cal-protein*4-carb*4)/9))
    return {"calories":cal,"protein_g":protein,"carbs_g":carb,"fat_g":fat,"refuel_day":hard}
def hydration(c,strain):
    base=WEIGHT*33; sweat=(c or 0)*1.0; total=round(base+sweat)
    return {"water_l":round(total/1000,1),"sodium_mg":2000+round((sweat/1000)*800),
        "note":"Add an electrolyte tab to ~1L today" if strain>=12 else "Normal electrolytes today"}
def tss_from_strain(strain,dur):
    if not strain: return 0.0
    base=(strain**2)*0.5
    if dur: base*=min(1.5,max(0.6,dur/60))
    return round(base,1)
def coach_template(rec,tsb,m,h,debt):
    if rec>=67: load="Green recovery - good day for a quality session or intervals."
    elif rec>=34: load="Yellow recovery - moderate aerobic work; keep intensity in check."
    else: load="Red recovery - prioritise easy Z1-Z2 or rest. Don't force it."
    form=""
    if tsb<-20: form=" You're carrying heavy fatigue - watch for overreaching."
    elif tsb>10: form=" You're fresh - a good window to race or test."
    return (f"{load}{form} Fuel ~{m['calories']} kcal: {m['protein_g']}g protein, {m['carbs_g']}g carbs, "
        f"{m['fat_g']}g fat{' (refuel day)' if m['refuel_day'] else ''}. Hydrate to ~{h['water_l']}L with "
        f"~{h['sodium_mg']}mg sodium; {h['note'].lower()}. Protect sleep tonight to clear {debt}h of sleep debt.")
def coach_openai(payload):
    global _last_error
    if not OPENAI_KEY: return None
    day=payload.get("date","")
    if day in _brief_cache: return _brief_cache[day]
    system=("You are an elite endurance coach and sports nutritionist. From the athlete's WHOOP recovery, "
        "HRV, sleep, strain and CTL/ATL/TSB plus computed calorie/macro/hydration targets, give a short, "
        "direct, actionable daily briefing (max ~120 words): how to train today, fuelling emphasis, hydration, "
        "one recovery action. Encouraging, never alarmist. No headers.")
    body=json.dumps({"model":OPENAI_MODEL,"temperature":0.5,
        "messages":[{"role":"system","content":system},{"role":"user","content":json.dumps(payload)}]}).encode()
    req=urllib.request.Request("https://api.openai.com/v1/chat/completions",data=body,
        headers={"Authorization":f"Bearer {OPENAI_KEY}","Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            out=json.loads(r.read())
        text=out["choices"][0]["message"]["content"].strip(); _brief_cache[day]=text; return text
    except urllib.error.HTTPError as e:
        _last_error=f"openai HTTP {e.code}: {e.read().decode()[:300]}"; return None
    except Exception as e:
        _last_error=f"openai {type(e).__name__}: {e}"; return None
def build_mock(n=14):
    today=dt.date.today(); days=[today-dt.timedelta(days=i) for i in range(n-1,-1,-1)]
    rows,ctl,atl=[],0.0,0.0
    for d in days:
        w=mock_day(d); tss=tss_from_strain(w["strain"],w["duration_min"])
        nc=ctl+(tss-ctl)/42.0; na=atl+(tss-atl)/7.0; tsb=ctl-atl
        td=tdee(w["calories_burned"]); m=macros(td,w["strain"],w["recovery_pct"]); h=hydration(w["calories_burned"],w["strain"])
        rows.append({**w,"tdee":td,"tss":tss,"ctl":round(nc,1),"atl":round(na,1),"tsb":round(tsb,1),
            "cal_target":m["calories"],"protein_g":m["protein_g"],"carbs_g":m["carbs_g"],"fat_g":m["fat_g"],
            "water_l":h["water_l"],"sodium_mg":h["sodium_mg"],
            "recommendation":coach_template(w["recovery_pct"],tsb,m,h,w["sleep_debt_hours"])})
        ctl,atl=nc,na
    return rows
def get_rows(n):
    if whoop_configured():
        live=build_recent_live(n)
        if live:
            t=live[-1]; ai=coach_openai({k:v for k,v in t.items() if v is not None})
            if ai: t["recommendation"]=ai
            return live,"live"
    rows=build_mock(n); t=rows[-1]; ai=coach_openai(t)
    if ai: t["recommendation"]=ai
    return rows,("ai" if OPENAI_KEY else "dry_run")

INDEX_HTML='<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n<title>Endurance Coach</title>\n<meta name="theme-color" content="#0b0f14">\n<link rel="manifest" href="/manifest.webmanifest">\n<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">\n<meta name="apple-mobile-web-app-capable" content="yes">\n<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">\n<meta name="apple-mobile-web-app-title" content="Coach">\n<link rel="stylesheet" href="/styles.css">\n</head>\n<body>\n<div id="app">\n  <header class="topbar">\n    <div>\n      <div class="hello" id="hello">Loading…</div>\n      <div class="date" id="date"></div>\n    </div>\n    <button id="refresh" class="refresh" aria-label="Refresh">⟳</button>\n  </header>\n\n  <main id="content" class="content">\n    <div class="skeleton">Fetching today\'s data…</div>\n  </main>\n\n  <footer class="foot">\n    <span id="mode"></span>\n  </footer>\n</div>\n<script src="/app.js"></script>\n</body>\n</html>\n'
STYLES_CSS=':root{\n  --bg:#0b0f14; --bg2:#121822; --card:#161e2a; --line:#222e3e;\n  --txt:#e8eef6; --muted:#8a99ad; --accent:#36d399; --accent2:#3aa0ff;\n  --warn:#fbbf24; --bad:#f87171; --good:#36d399;\n  --radius:18px;\n}\n*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}\nhtml,body{margin:0;background:var(--bg);color:var(--txt);\n  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}\n#app{max-width:520px;margin:0 auto;padding:\n  env(safe-area-inset-top) 16px calc(env(safe-area-inset-bottom) + 16px)}\n.topbar{display:flex;justify-content:space-between;align-items:center;\n  padding:18px 2px 12px}\n.hello{font-size:22px;font-weight:700;letter-spacing:.2px}\n.date{color:var(--muted);font-size:13px;margin-top:2px}\n.refresh{background:var(--card);border:1px solid var(--line);color:var(--txt);\n  width:42px;height:42px;border-radius:50%;font-size:20px;cursor:pointer}\n.refresh:active{transform:rotate(90deg)}\n.content{display:flex;flex-direction:column;gap:14px}\n.skeleton{color:var(--muted);text-align:center;padding:60px 0}\n\n.card{background:var(--card);border:1px solid var(--line);\n  border-radius:var(--radius);padding:16px}\n.card h3{margin:0 0 12px;font-size:13px;font-weight:600;color:var(--muted);\n  text-transform:uppercase;letter-spacing:.6px}\n\n/* hero: recovery ring + two stats */\n.hero{display:grid;grid-template-columns:1.1fr 1fr;gap:12px;align-items:center}\n.ring-wrap{position:relative;width:140px;height:140px;margin:0 auto}\n.ring{display:block;width:140px;height:140px}\n.val{position:absolute;top:0;left:0;right:0;height:140px;display:flex;\n  flex-direction:column;align-items:center;justify-content:center;pointer-events:none}\n.num{font-size:34px;font-weight:800;line-height:1}\n.lbl{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-top:4px}\n.heros{display:flex;flex-direction:column;gap:12px}\n.stat{background:var(--bg2);border-radius:14px;padding:12px 14px}\n.stat .k{font-size:12px;color:var(--muted)}\n.stat .v{font-size:24px;font-weight:700;margin-top:2px}\n.stat .v small{font-size:13px;color:var(--muted);font-weight:500}\n\n/* biometric grid */\n.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}\n.metric{background:var(--bg2);border-radius:14px;padding:12px 14px}\n.metric .k{font-size:12px;color:var(--muted)}\n.metric .v{font-size:22px;font-weight:700;margin-top:2px}\n.metric .v small{font-size:12px;color:var(--muted);font-weight:500}\n.spark{margin-top:8px;height:34px;width:100%}\n\n/* macros */\n.macros{display:flex;flex-direction:column;gap:10px}\n.cal{font-size:30px;font-weight:800}\n.cal small{font-size:13px;color:var(--muted);font-weight:500}\n.bar{height:10px;border-radius:6px;background:var(--bg2);overflow:hidden;margin-top:6px}\n.bar > span{display:block;height:100%}\n.mrow{display:flex;justify-content:space-between;font-size:13px;margin-bottom:2px}\n.mrow b{font-weight:700}\n.tag{display:inline-block;font-size:11px;padding:3px 8px;border-radius:20px;\n  background:rgba(54,211,153,.15);color:var(--good);margin-top:4px}\n\n/* pmc */\n.pmc{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;text-align:center}\n.pmc .k{font-size:11px;color:var(--muted);text-transform:uppercase}\n.pmc .v{font-size:22px;font-weight:800;margin-top:2px}\n.chart{margin-top:12px;width:100%;height:90px}\n\n/* hydration */\n.hyd{display:flex;align-items:center;gap:14px}\n.drop{font-size:34px}\n.hyd .big{font-size:26px;font-weight:800}\n.hyd .sub{color:var(--muted);font-size:13px}\n\n/* coach */\n.coach{background:linear-gradient(160deg,#16314a,#161e2a);border-color:#21405c}\n.coach p{margin:0;line-height:1.5;font-size:15px}\n.coach .by{margin-top:10px;font-size:12px;color:var(--muted)}\n\n.foot{text-align:center;color:var(--muted);font-size:11px;padding:18px 0 6px}\n.badge{display:inline-block;padding:2px 8px;border-radius:20px;\n  border:1px solid var(--line)}\n'
APP_JS='const $ = (s) => document.querySelector(s);\nconst num = (x, d=0) => (x===null||x===undefined||x===\'\') ? \'–\' : (+x).toFixed(d);\n\nfunction recoveryColor(p){\n  if(p===null||p===undefined) return \'var(--muted)\';\n  if(p>=67) return \'var(--good)\';\n  if(p>=34) return \'var(--warn)\';\n  return \'var(--bad)\';\n}\n\nfunction ring(pct, color){\n  const r=62, c=2*Math.PI*r, v=Math.max(0,Math.min(100,pct||0));\n  const off=c*(1-v/100);\n  return `<svg class="ring" viewBox="0 0 140 140">\n    <circle cx="70" cy="70" r="${r}" fill="none" stroke="var(--bg2)" stroke-width="12"/>\n    <circle cx="70" cy="70" r="${r}" fill="none" stroke="${color}" stroke-width="12"\n      stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${off}"\n      transform="rotate(-90 70 70)"/>\n  </svg>`;\n}\n\n// 7-day bar sparkline\nfunction bars(values, color){\n  const v=values.filter(x=>x!==null&&x!==undefined&&x!==\'\');\n  if(!v.length) return \'\';\n  const max=Math.max(...v), min=Math.min(...v), span=(max-min)||1;\n  const n=values.length, w=100/n;\n  return `<svg class="spark" viewBox="0 0 100 34" preserveAspectRatio="none">`+\n    values.map((x,i)=>{\n      if(x===null||x===\'\'||x===undefined) return \'\';\n      const h=6+28*((x-min)/span);\n      return `<rect x="${i*w+1}" y="${34-h}" width="${w-2}" height="${h}" rx="1.5" fill="${color}"/>`;\n    }).join(\'\')+`</svg>`;\n}\n\n// simple 2-line chart (CTL vs ATL)\nfunction lineChart(ctl, atl){\n  const all=[...ctl,...atl].filter(x=>x!==null&&x!==\'\');\n  if(!all.length) return \'\';\n  const max=Math.max(...all,1), n=ctl.length, W=100, H=90;\n  const pts=(arr)=>arr.map((x,i)=>`${(i/(n-1||1))*W},${H-(x/max)*H}`).join(\' \');\n  return `<svg class="chart" viewBox="0 0 100 90" preserveAspectRatio="none">\n    <polyline points="${pts(ctl)}" fill="none" stroke="var(--accent2)" stroke-width="2"/>\n    <polyline points="${pts(atl)}" fill="none" stroke="var(--warn)" stroke-width="2" stroke-dasharray="3 3"/>\n  </svg>`;\n}\n\nfunction macroBar(g, kcalPerG, total, color){\n  const pct = total ? Math.min(100,(g*kcalPerG/total)*100) : 0;\n  return `<span style="width:${pct}%;background:${color}"></span>`;\n}\n\nfunction render(data){\n  const rows=data.rows||[];\n  $(\'#hello\').textContent = `Hey ${data.athlete||\'athlete\'}`;\n  $(\'#mode\').innerHTML = `<span class="badge">${data.mode===\'live\'?\'live data\':\'demo data\'}</span>`;\n  if(!rows.length){ $(\'#content\').innerHTML=\'<div class="skeleton">No data yet. Run the daily job.</div>\'; return; }\n\n  const t=rows[rows.length-1];\n  const last7=rows.slice(-7);\n  $(\'#date\').textContent = new Date(t.date+\'T00:00\').toLocaleDateString(undefined,\n    {weekday:\'long\',month:\'short\',day:\'numeric\'});\n\n  const rc=recoveryColor(+t.recovery_pct);\n  const calT=+t.cal_target||0;\n  const refuel = (+t.carbs_g*4) > (+t.cal_target*0.5);\n\n  $(\'#content\').innerHTML = `\n    <section class="card hero">\n      <div class="ring-wrap">\n        ${ring(+t.recovery_pct, rc)}\n        <div class="val">\n          <div class="num" style="color:${rc}">${num(t.recovery_pct)}<small style="font-size:16px">%</small></div>\n          <div class="lbl">Recovery</div>\n        </div>\n      </div>\n      <div class="heros">\n        <div class="stat"><div class="k">Day Strain</div>\n          <div class="v">${num(t.strain,1)} <small>/ 21</small></div></div>\n        <div class="stat"><div class="k">Sleep</div>\n          <div class="v">${num(t.sleep_hours,1)}<small>h · ${num(t.sleep_performance_pct)}%</small></div></div>\n      </div>\n    </section>\n\n    <section class="card">\n      <h3>Biometrics</h3>\n      <div class="grid">\n        <div class="metric"><div class="k">HRV (7-day)</div>\n          <div class="v">${num(t.hrv_ms)}<small> ms</small></div>\n          ${bars(last7.map(r=>+r.hrv_ms),\'var(--accent)\')}</div>\n        <div class="metric"><div class="k">Resting HR</div>\n          <div class="v">${num(t.resting_hr)}<small> bpm</small></div>\n          ${bars(last7.map(r=>+r.resting_hr),\'var(--accent2)\')}</div>\n        <div class="metric"><div class="k">Sleep debt</div>\n          <div class="v">${num(t.sleep_debt_hours,1)}<small> h</small></div></div>\n        <div class="metric"><div class="k">TDEE burned</div>\n          <div class="v">${num(t.tdee)}<small> kcal</small></div></div>\n        <div class="metric"><div class="k">Respiratory</div>\n          <div class="v">${num(t.respiratory_rate,1)}<small> br/m</small></div></div>\n        <div class="metric"><div class="k">Calories out</div>\n          <div class="v">${num(t.calories_burned)}<small> kcal</small></div></div>\n      </div>\n    </section>\n\n    <section class="card">\n      <h3>Training Load · Performance Mgmt</h3>\n      <div class="pmc">\n        <div><div class="k">Fitness · CTL</div><div class="v">${num(t.ctl,1)}</div></div>\n        <div><div class="k">Fatigue · ATL</div><div class="v" style="color:var(--warn)">${num(t.atl,1)}</div></div>\n        <div><div class="k">Form · TSB</div><div class="v" style="color:${(+t.tsb)>=0?\'var(--good)\':\'var(--bad)\'}">${num(t.tsb,1)}</div></div>\n      </div>\n      ${lineChart(rows.map(r=>+r.ctl), rows.map(r=>+r.atl))}\n      <div style="font-size:11px;color:var(--muted);margin-top:6px">\n        <span style="color:var(--accent2)">▬ CTL</span> &nbsp;\n        <span style="color:var(--warn)">▬ ATL</span></div>\n    </section>\n\n    <section class="card">\n      <h3>Today\'s Fuel</h3>\n      <div class="cal">${num(t.cal_target)}<small> kcal target</small></div>\n      ${refuel?\'<span class="tag">refuel / carb-load day</span>\':\'\'}\n      <div class="macros" style="margin-top:10px">\n        <div>\n          <div class="mrow"><span>Protein</span><b>${num(t.protein_g)} g</b></div>\n          <div class="bar">${macroBar(+t.protein_g,4,calT,\'var(--accent)\')}</div></div>\n        <div>\n          <div class="mrow"><span>Carbs</span><b>${num(t.carbs_g)} g</b></div>\n          <div class="bar">${macroBar(+t.carbs_g,4,calT,\'var(--accent2)\')}</div></div>\n        <div>\n          <div class="mrow"><span>Fat</span><b>${num(t.fat_g)} g</b></div>\n          <div class="bar">${macroBar(+t.fat_g,9,calT,\'var(--warn)\')}</div></div>\n      </div>\n    </section>\n\n    <section class="card">\n      <h3>Hydration</h3>\n      <div class="hyd">\n        <div class="drop">💧</div>\n        <div>\n          <div class="big">${num(t.water_l,1)} L</div>\n          <div class="sub">+ ${num(t.sodium_mg)} mg sodium today</div>\n        </div>\n      </div>\n    </section>\n\n    <section class="card coach">\n      <h3 style="color:#9fd0ff">Coach</h3>\n      <p>${(t.recommendation||\'\').replace(/</g,\'&lt;\')}</p>\n      <div class="by">AI-generated from today\'s recovery, load & fuel</div>\n    </section>\n  `;\n}\n\nasync function load(){\n  try{\n    const r=await fetch(\'/api/data?days=14\',{cache:\'no-store\'});\n    const data=await r.json();\n    render(data);\n  }catch(e){\n    $(\'#content\').innerHTML=\'<div class="skeleton">Offline — showing nothing new. Pull to refresh when back online.</div>\';\n  }\n}\n\n$(\'#refresh\').addEventListener(\'click\',load);\nload();\n\nif(\'serviceWorker\' in navigator){\n  navigator.serviceWorker.register(\'/service-worker.js\').catch(()=>{});\n}\n'
MANIFEST='{\n  "name": "Endurance Coach",\n  "short_name": "Coach",\n  "description": "Daily recovery, training load and nutrition coaching from your WHOOP & TrainingPeaks data.",\n  "start_url": "/",\n  "scope": "/",\n  "display": "standalone",\n  "orientation": "portrait",\n  "background_color": "#0b0f14",\n  "theme_color": "#0b0f14",\n  "icons": [\n    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any" },\n    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any" },\n    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }\n  ]\n}\n'
SW_JS="// App-shell cache + network-first data, so the PWA opens offline.\nconst CACHE = 'coach-v1';\nconst SHELL = ['/', '/index.html', '/styles.css', '/app.js',\n  '/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png'];\n\nself.addEventListener('install', (e) => {\n  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));\n});\n\nself.addEventListener('activate', (e) => {\n  e.waitUntil(caches.keys().then((keys) =>\n    Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))\n  ).then(() => self.clients.claim()));\n});\n\nself.addEventListener('fetch', (e) => {\n  const url = new URL(e.request.url);\n  if (url.pathname.startsWith('/api/')) {\n    // network-first for live data, fall back to last cached response\n    e.respondWith(\n      fetch(e.request).then((r) => {\n        const copy = r.clone();\n        caches.open(CACHE).then((c) => c.put(e.request, copy));\n        return r;\n      }).catch(() => caches.match(e.request))\n    );\n  } else {\n    // cache-first for the app shell\n    e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));\n  }\n});\n"
ICON_192=base64.b64decode('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'); ICON_512=base64.b64decode('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'); ICON_APPLE=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAALQAAAC0CAIAAACyr5FlAAAFjklEQVR4nO3dO24UQRRG4TIiA4GFICJFIiFgBUReiTfBGrwXlkDECghILLEDS8iyvACCQq2mx39PP+pW9b11vghLZsbqOnO7uv2Yixev3ybgKc9afwE4LuKARByQiAMScUAiDkjEAYk4IBEHJOKARByQiAMScUAiDkjEAYk4IBEHJOKARByQiAMScUAiDkjEAYk4ID1v8qxvPn1p8ryu/fn1o/IzXtT8jTeaKKJaJZXimGTx8PtnhScN5tWHz+MPKyRSI45xGWSx0zgR6z7M4xjKIIuChkRM+7CNI5dBFkZyInZ9GF7KUoa1fGzttvlWcVBGHaZ9mMRBGTXZ9VE+Dm5mtFL8yFudVhgbNRkd7cJxMDbaKnv8TSYHY6M+i2POd2UhlYyDi5S2il+2MDkgEQck4oDU5ifBjuPl5bvxh++/XU8+4fbqpuKXcyzdxTGp4ayP37+OP+yqlV7iWNuEMrTSQyXx4yiVxUSuJHYikeMwymIsdiIx46iQxVjURAJeylYuYzDZugYQLY5WZWTB+ohzWtmWxeP93fjD01PD2vWOdIoJEseqMiZBzBsv8/JQPn7/GqCPCKeV5WU83t+tKmPi9upm+ZIHOMW4j2NhGTuzGFueiPc+fMexpIyCWYwtTMR1H47jWFiG6dcQu48gG9JT1lkMch9+C5jhdXLMj41qZQzmR4jTdFzGcbQysnh9+IvjmGVkwfoItefYVsaGNZuJ4Pbqxl0EirPJ0fZbJ9meW5++unEWx4xqY+OsADfOM09xzIyNyheuez7N0fDwFEdxjtapCTdxOBobZz/ZS5Ru4mguzE5iOfdxbB4bFV6+3nvyEUfzK9jiy+zizOIjDqXO2NhThuvh4TsOmCKOM1y/9HfqMQ4X5/sjcBCH2o1WuL1RZGyoBzl+ow7iaKXnE0rWXRzHf70eR3dxLMTYSL3FsXBsUEbWVxxYhTimGBuDjuJgK7pWqB8wLmKmod6GSi+TY//Y6K2M1E8cO3VYRnJxWnm8v3vyDvrLy3fL76A3/I1n9bDHD47J8Q9bjVPEcUa3ZSTiyPxOflOO43j/7dr01kWRMlzfXHGwIU0ne9LTN77Yo8n6uZhJPuLInmzC6I86MjaSo9NK2Wkxz8XLugI3cRj9duHp/y1VRoBrYzdx1OFl2erwFEfx4WG3JwgwNpKvOOYd51tr3vehA2dxFHzZNXlnP0djI7mLY97ml6xdc675i6PIn3Mcf1q1MnyNjeQxjnTUP/cZrIzkNI5Uro86m1CPZSRft89XmXk7rbJvHBxpkzHhdXKk3T/cVa0Mp2MjuY4jLe5jvISl3qBv8rCK3zKS9zjS4qO/cC3LPpTrMlKAONKaNdg5NlYV5r2MFGZDuuq9Clbd5Ng2bwKUkcLEkba+nVbxa40YWWQRTitjbdcmUhkpXhyp3QoFKyNFOq2MVX7HxnhZZDHjyCokEjWLLHIcmVEisbPI4seRDWu5s5Iemhj0EsdgsrpnW+mqhonu4pjoee3PCngpi1KIAxJxQCIOSMQBiTggEQck4oBEHJCIAxJxQCIOSMQBiTggEQck4oBEHJCIAxJxQCIOSMQBiTggEQck4oBEHJBKxvHn14+U0qsPnws+JpbLRz6vQhFMDkgmcTA86rM45oXjKDjTsEHZ4291WmF41GR0tMvHwfBopfiRN5kcXLbUVPwiZWB1WqGPOuzKSKaXsvRhzbSMlNLFi9dvjR46e/PpS/7Hw++fpk/UleElZ7rDM48jjfpIJLLbeBJb7/1rxJH+7yORyCaTE3SFq8JKcWSTRLBNtZsFVeMYUMkG9W8gtYkDLvBdWUjEAYk4IBEHJOKARByQiAMScUAiDkjEAYk4IBEHJOKARByQiAMScUAiDkjEAYk4IBEHJOKARByQiAPSX7Dh9VN1Sj5fAAAAAElFTkSuQmCC')

@app.route("/")
def index(): return Response(INDEX_HTML,mimetype="text/html")
@app.route("/styles.css")
def css(): return Response(STYLES_CSS,mimetype="text/css")
@app.route("/app.js")
def js(): return Response(APP_JS,mimetype="application/javascript")
@app.route("/manifest.webmanifest")
def man(): return Response(MANIFEST,mimetype="application/manifest+json")
@app.route("/service-worker.js")
def sw(): return Response(SW_JS,mimetype="application/javascript")
@app.route("/icons/icon-192.png")
def i192(): return Response(ICON_192,mimetype="image/png")
@app.route("/icons/icon-512.png")
def i512(): return Response(ICON_512,mimetype="image/png")
@app.route("/icons/apple-touch-icon.png")
def iapple(): return Response(ICON_APPLE,mimetype="image/png")

@app.route("/api/data")
def data():
    days=int(request.args.get("days",14)); rows,source=get_rows(days)
    return jsonify({"athlete":ATHLETE,"goal":GOAL,"mode":source,"rows":rows})

@app.route("/whoop/login")
def whoop_login():
    if not whoop_configured():
        return Response("WHOOP not configured. Set WHOOP_CLIENT_ID and WHOOP_CLIENT_SECRET in Render.",mimetype="text/plain")
    state=base64.urlsafe_b64encode(os.urandom(6)).decode()
    p=urllib.parse.urlencode({"response_type":"code","client_id":WHOOP_ID,
        "redirect_uri":WHOOP_REDIRECT,"scope":WHOOP_SCOPES,"state":state})
    return redirect(f"{WHOOP_AUTH}?{p}")

@app.route("/whoop/callback")
def whoop_callback():
    err=request.args.get("error")
    if err: return Response(f"WHOOP returned an error: {err}",mimetype="text/plain")
    code=request.args.get("code")
    if not code: return Response("No code from WHOOP.",mimetype="text/plain")
    tok=whoop_exchange(code)
    if not tok or not tok.get("access_token"):
        return Response(f"Could not get WHOOP token. {_last_error or ''}",mimetype="text/plain")
    kv_set("whoop:token",json.dumps(tok))
    return redirect("/?connected=1")

@app.route("/whoop/status")
def whoop_status():
    return jsonify({"whoop_configured":whoop_configured(),"whoop_connected":whoop_connected(),
        "upstash_set":bool(UPSTASH_URL and UPSTASH_TOKEN),"openai_set":bool(OPENAI_KEY),
        "redirect_uri":WHOOP_REDIRECT,"last_error":_last_error})

@app.route("/diag")
def diag():
    _brief_cache.clear()
    test=coach_openai({"date":"diag","recovery_pct":70,"strain":10,"tdee":2800,"ctl":40,"atl":35,
        "tsb":5,"cal_target":2800,"protein_g":135,"carbs_g":300,"fat_g":90,"water_l":3,"sodium_mg":2500,
        "sleep_debt_hours":0.5,"hrv_ms":80,"resting_hr":50,"sleep_hours":7})
    return jsonify({"openai_set":bool(OPENAI_KEY),"openai_success":bool(test),
        "whoop_configured":whoop_configured(),"whoop_connected":whoop_connected(),
        "upstash_set":bool(UPSTASH_URL and UPSTASH_TOKEN),"error":_last_error})

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",8000)))
