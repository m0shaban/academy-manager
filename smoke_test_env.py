import json
import os
import importlib
from pathlib import Path


def load_dotenv_simple(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")):
            value = value[1:-1]
        os.environ[key] = value


def main() -> None:
    env_path = Path(r"F:\Raw\New folder\academy-manager (1).env")
    if not env_path.exists():
        raise SystemExit(f"Env file not found: {env_path}")

    load_dotenv_simple(env_path)

    import webhook

    importlib.reload(webhook)

    admin = os.environ.get("ADMIN_TOKEN", "")
    client = webhook.app.test_client()
    resp = client.get("/self-test", headers={"X-Admin-Token": admin})

    print("HTTP", resp.status_code)
    payload = resp.get_json() or {}
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
