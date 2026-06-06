"""
Run the daily pipeline automatically.

    python scheduler.py            # runs every day at 07:00 local time

Keep this process alive (a terminal, tmux, or a service). For an always-on
setup, see the README section "Deploy it" (cron / Render / Railway).
"""
import time

import schedule

import main

RUN_AT = "07:00"


def job():
    try:
        main.main()
    except Exception as e:
        print("Run failed:", e)


schedule.every().day.at(RUN_AT).do(job)

if __name__ == "__main__":
    print(f"Scheduler started — will run daily at {RUN_AT}. Ctrl-C to stop.")
    job()  # run once on start
    while True:
        schedule.run_pending()
        time.sleep(30)
