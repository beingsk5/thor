import requests
import os
import json

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"
REPOS_FILE = "repos.json"

def send_channel_message(text):
    requests.post(f"{TELEGRAM_API}/sendMessage", json={
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "Markdown"
    })

def get_latest_release(repo):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    r = requests.get(url)
    return r.json() if r.status_code == 200 else None

def main():
    if not os.path.exists(REPOS_FILE):
        print("No repos to check.")
        return

    repos = json.load(open(REPOS_FILE))
    updated = False

    for repo, last_tag in repos.items():
        latest = get_latest_release(repo)
        if not latest:
            continue

        if latest["tag_name"] != last_tag:
            send_channel_message(
                f"🚀 *New Release for {repo}*\n\n*{latest['name']}* (`{latest['tag_name']}`)\n{latest['html_url']}"
            )
            repos[repo] = latest["tag_name"]
            updated = True

    if updated:
        with open(REPOS_FILE, "w") as f:
            json.dump(repos, f, indent=2)

if __name__ == "__main__":
    main()
