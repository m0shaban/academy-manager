import os
import time

import requests


BACKEND_URL = os.environ.get("BACKEND_URL", "").rstrip("/")
CRON_SECRET = os.environ.get("CRON_SECRET", "")
INTERVAL_SECONDS = int(os.environ.get("PUBLISHER_INTERVAL_SECONDS", "60") or "60")


def tick() -> None:
    if not BACKEND_URL:
        raise SystemExit("BACKEND_URL is missing")
    if not CRON_SECRET:
        raise SystemExit("CRON_SECRET is missing")

    url = f"{BACKEND_URL}/publisher-tick"
    resp = requests.get(url, params={"secret": CRON_SECRET}, timeout=20)
    print(resp.status_code, resp.text[:500])


def main() -> None:
    while True:
        try:
            tick()
        except Exception as e:
            print("tick error:", str(e))
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
