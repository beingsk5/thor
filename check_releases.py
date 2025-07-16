# check_releases.py

import requests
import os
import json

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"
REPOS_FILE = "repos.json"
HISTORY_FILE = "history.json"
TELEGRAM_FILE_LIMIT_MB = 50

def send_channel_message(text, buttons=None):
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}

    try:
        requests.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        print(f"[Telegram Error] {e}")

def send_telegram_file(url, filename):
    try:
        file_bytes = requests.get(url, timeout=20).content
        if len(file_bytes) > TELEGRAM_FILE_LIMIT_MB * 1024 * 1024:
            return False
        files = {'document': (filename, file_bytes)}
        data = {'chat_id': CHANNEL_ID}
        requests.post(f"{TELEGRAM_API}/sendDocument", data=data, files=files, timeout=30)
        return True
    except:
        return False

def get_latest_release(repo):
    try:
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        r = requests.get(url, timeout=10)
        return r.json() if r.status_code == 200 else None
    except:
        return None

def load_file(path):
    return json.load(open(path)) if os.path.exists(path) else {}

def save_file(data, path):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def main():
    repos = load_file(REPOS_FILE)
    history = load_file(HISTORY_FILE)
    updated = False

    for repo, last_tag in repos.items():
        latest = get_latest_release(repo)
        if not latest or "tag_name" not in latest:
            continue

        if latest["tag_name"] != last_tag:
            msg = f"🚀 *New Release for `{repo}`!*\n*{latest.get('name', 'Unnamed')}* (`{latest['tag_name']}`)"
            assets = latest.get("assets", [])
            buttons = []

            for asset in assets:
                name = asset.get("name")
                url = asset.get("browser_download_url")

                uploaded = send_telegram_file(url, name)
                if not uploaded:
                    buttons.append([{"text": f"🔽 {name}", "url": url}])

            send_channel_message(msg, buttons if buttons else None)
            repos[repo] = latest["tag_name"]

            history.setdefault(repo, []).append(latest["tag_name"])
            updated = True

    if updated:
        save_file(repos, REPOS_FILE)
        save_file(history, HISTORY_FILE)
        print("[🔁] Updated repos and history.")

if __name__ == "__main__":
    main()
