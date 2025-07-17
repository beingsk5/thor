import os
import json
import requests

REPO_FILE = "repos.json"
HISTORY_FILE = "history.json"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

def load_json(path, fallback):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(fallback, f)
    with open(path) as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": msg,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    return requests.post(url, json=payload)

def main():
    repos = load_json(REPO_FILE, [])
    history = load_json(HISTORY_FILE, {})

    for repo in repos:
        try:
            r = requests.get(f"https://api.github.com/repos/{repo}/releases/latest", timeout=10)
            if r.status_code != 200:
                continue
            data = r.json()
            latest_tag = data["tag_name"]
            release_url = data["html_url"]
            if repo not in history or history[repo]["tag"] != latest_tag:
                msg = f"🚀 New release for *{repo}*:\n[{latest_tag}]({release_url})"
                send_telegram(msg)
                history[repo] = {"tag": latest_tag, "url": release_url}
        except Exception as e:
            print(f"Error for {repo}: {e}")

    save_json(HISTORY_FILE, history)

if __name__ == "__main__":
    main()
