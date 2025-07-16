import requests
import os
import json

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"
REPOS_FILE = "repos.json"
HISTORY_FILE = "history.json"

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

def update_badge(count):
    badge_svg = f'''
<svg xmlns="http://www.w3.org/2000/svg" width="140" height="20">
  <linearGradient id="a" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <rect rx="3" width="140" height="20" fill="#555"/>
  <rect rx="3" x="80" width="60" height="20" fill="#4c1"/>
  <path fill="#4c1" d="M80 0h4v20h-4z"/>
  <rect rx="3" width="140" height="20" fill="url(#a)"/>
  <g fill="#fff" font-family="Verdana" font-size="11">
    <text x="6" y="14">Tracked Repos</text>
    <text x="90" y="14">{count}</text>
  </g>
</svg>
'''
    os.makedirs("badges", exist_ok=True)
    with open("badges/tracked_count_badge.svg", "w") as f:
        f.write(badge_svg)

def main():
    if not os.path.exists(REPOS_FILE):
        print("No repos to check.")
        return

    repos = json.load(open(REPOS_FILE))
    history = json.load(open(HISTORY_FILE)) if os.path.exists(HISTORY_FILE) else {}

    updated = False

    for repo, last_tag in repos.items():
        latest = get_latest_release(repo)
        if not latest or "tag_name" not in latest:
            continue

        if latest["tag_name"] != last_tag:
            send_channel_message(
                f"🚀 *New Release for {repo}*\n\n*{latest['name']}* (`{latest['tag_name']}`)\n{latest['html_url']}"
            )
            repos[repo] = latest["tag_name"]
            history.setdefault(repo, []).append(latest["tag_name"])
            updated = True

    if updated:
        with open(REPOS_FILE, "w") as f:
            json.dump(repos, f, indent=2)
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)

    update_badge(len(repos))

if __name__ == "__main__":
    main()
