import requests
import os
import json

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
REPOS_FILE = "repos.json"

def send_message(text):
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)

def get_latest_release(repo):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None

def main():
    if not os.path.exists(REPOS_FILE):
        print("No repos.json found.")
        return

    with open(REPOS_FILE, "r") as f:
        repos = json.load(f)

    updated = False

    for repo, last_tag in repos.items():
        latest = get_latest_release(repo)
        if latest and latest["tag_name"] != last_tag:
            message = f"🚀 New release for *{repo}*:\n\n*{latest['name']}* (`{latest['tag_name']}`)\n{latest['html_url']}"
            send_message(message)
            repos[repo] = latest["tag_name"]
            updated = True

    if updated:
        with open(REPOS_FILE, "w") as f:
            json.dump(repos, f, indent=2)

if __name__ == "__main__":
    main()
