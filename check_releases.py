import requests
import os
import json

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"
REPOS_FILE = "repos.json"
HISTORY_FILE = "history.json"

def send_channel_message(text, buttons=None):
    try:
        data = {
            "chat_id": CHANNEL_ID,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        if buttons:
            data["reply_markup"] = {"inline_keyboard": buttons}
        requests.post(f"{TELEGRAM_API}/sendMessage", json=data, timeout=15)
    except Exception as e:
        print(f"[SEND MSG ERROR] {e}")

def send_document(file_url, filename):
    try:
        file = requests.get(file_url, timeout=10)
        if file.status_code == 200 and len(file.content) < 45 * 1024 * 1024:
            files = {"document": (filename, file.content)}
            data = {"chat_id": CHANNEL_ID, "caption": f"💾 `{filename}`", "parse_mode": "Markdown"}
            requests.post(f"{TELEGRAM_API}/sendDocument", files=files, data=data, timeout=30)
    except Exception as e:
        print(f"[UPLOAD ERROR] {filename} → {e}")

def safe_get(url, timeout=10):
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        else:
            print(f"[HTTP Error] {url} → {r.status_code}")
    except Exception as e:
        print(f"[Request Failed] {url} → {e}")
    return None

def load_file(path):
    return json.load(open(path)) if os.path.exists(path) else {}

def save_file(data, path):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def load_repos_from_env():
    raw = os.getenv("TRACKED_REPOS", "")
    repos = {}
    for r in raw.split(","):
        r = r.strip()
        if r:
            repos[r] = ""
    return repos

def main():
    repos = load_file(REPOS_FILE)
    if not repos:
        repos = load_repos_from_env()
        save_file(repos, REPOS_FILE)

    history = load_file(HISTORY_FILE)
    updated = False

    for repo, last_tag in repos.items():
        latest = safe_get(f"https://api.github.com/repos/{repo}/releases/latest")
        if not latest or "tag_name" not in latest:
            continue

        tag = latest["tag_name"]
        if tag != last_tag:
            name = latest.get("name", tag)
            html_url = latest.get("html_url", "")
            text = f"🚀 *New Release for* `{repo}`\n\n*{name}* (`{tag}`)"

            buttons = []
            if latest.get("assets"):
                for asset in latest["assets"]:
                    url = asset["browser_download_url"]
                    name = asset["name"]
                    size = asset["size"]

                    if size < 45 * 1024 * 1024:
                        send_document(url, name)
                    else:
                        buttons.append([{"text": f"⬇️ {name}", "url": url}])

            buttons.append([{"text": "🌐 View on GitHub", "url": html_url}])
            send_channel_message(text, buttons=buttons)

            repos[repo] = tag
            history.setdefault(repo, []).append(tag)
            updated = True

    if updated:
        save_file(repos, REPOS_FILE)
        save_file(history, HISTORY_FILE)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[🔥 check_releases.py crashed] {e}")
