import os, requests, json, time, subprocess

TOKEN = os.getenv("TELEGRAM_TOKEN")
OWNER_ID = int(os.getenv("TELEGRAM_OWNER_ID"))
API = f"https://api.telegram.org/bot{TOKEN}"
REPOS_FILE = "repos.json"
HISTORY_FILE = "history.json"
BADGE_FILE = "badges/tracked_count_badge.svg"
PENDING = {}

def send_msg(chat_id, text, reply_to=None, buttons=None):
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_to: data["reply_to_message_id"] = reply_to
    if buttons:
        data["reply_markup"] = {"inline_keyboard": buttons}
    return requests.post(f"{API}/sendMessage", json=data).json()

def delete_msg(chat_id, msg_id):
    requests.post(f"{API}/deleteMessage", json={
        "chat_id": chat_id,
        "message_id": msg_id
    })

def get_updates(offset=None):
    params = {"timeout": 30, "offset": offset} if offset else {"timeout": 30}
    return requests.get(f"{API}/getUpdates", params=params).json().get("result", [])

def parse_repo(text):
    if "github.com/" in text:
        parts = text.split("github.com/")[1].split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1].split()[0]}"
    elif "/" in text and " " not in text:
        return text.strip()
    return None

def get_latest(repo):
    r = requests.get(f"https://api.github.com/repos/{repo}/releases/latest")
    return r.json() if r.status_code == 200 else None

def load_repos():
    if os.path.exists(REPOS_FILE):
        return json.load(open(REPOS_FILE))
    fallback = os.getenv("TRACKED_REPOS", "")
    repos = {r.strip(): "" for r in fallback.split(",") if "/" in r}
    save_repos(repos)
    return repos

def save_repos(r): 
    with open(REPOS_FILE, "w") as f: json.dump(r, f, indent=2)

def save_history(h): 
    with open(HISTORY_FILE, "w") as f: json.dump(h, f, indent=2)

def update_badge(count):
    os.makedirs("badges", exist_ok=True)
    svg = f'''
<svg xmlns="http://www.w3.org/2000/svg" width="140" height="20">
  <rect width="140" height="20" fill="#555"/>
  <rect x="80" width="60" height="20" fill="#4c1"/>
  <text x="6" y="14" fill="#fff" font-family="Verdana" font-size="11">Tracked Repos</text>
  <text x="90" y="14" fill="#fff" font-family="Verdana" font-size="11">{count}</text>
</svg>'''
    with open(BADGE_FILE, "w") as f: f.write(svg)

def git_push_changes():
    actor = os.getenv("GITHUB_ACTOR")
    repo = os.getenv("GITHUB_REPO")
    token = os.getenv("GH_PUSH_TOKEN")

    subprocess.run(["git", "config", "--global", "user.email", "bot@github.com"])
    subprocess.run(["git", "config", "--global", "user.name", "Im-Thor Bot"])

    subprocess.run(["git", "add", REPOS_FILE, HISTORY_FILE, BADGE_FILE])
    subprocess.run(["git", "commit", "-m", "🤖 Updated repos, history, and badge"], check=False)
    subprocess.run([
        "git", "push",
        f"https://{actor}:{token}@github.com/{repo}.git",
        "HEAD:main"
    ], check=False)

def handle_command(chat_id, text):
    repos = load_repos()
    if text == "/start":
        send_msg(chat_id, "👋 Welcome! Send a GitHub repo link or name to track new releases.")
    elif text == "/list":
        if repos:
            lines = [f"🔹 `{r}`" for r in repos.keys()]
            send_msg(chat_id, "*Tracked Repositories:*\n" + "\n".join(lines))
        else:
            send_msg(chat_id, "📭 No repositories are being tracked.")
    elif text == "/clearall":
        save_repos({})
        save_history({})
        update_badge(0)
        git_push_changes()
        send_msg(chat_id, "🗑️ Cleared all tracked repos.")
    elif text == "/ping":
        send_msg(chat_id, "🏓 Bot is alive!")
    elif text == "/about":
        send_msg(chat_id, "🤖 *Im-Thor GitHub Tracker*\nBuilt by @beingsk5\nTracks GitHub releases and updates your Telegram.")

def main():
    offset = None
    repos = load_repos()
    history = json.load(open(HISTORY_FILE)) if os.path.exists(HISTORY_FILE) else {}

    while True:
        for upd in get_updates(offset):
            offset = upd["update_id"] + 1

            if "message" in upd:
                msg = upd["message"]
                chat_id = msg["chat"]["id"]
                uid = msg["from"]["id"]
                text = msg.get("text", "")
                msg_id = msg["message_id"]

                if uid != OWNER_ID:
                    send_msg(chat_id, "⛔ You are not authorized.")
                    continue

                if text.startswith("/"):
                    handle_command(chat_id, text)
                    continue

                repos_added = 0
                new_repos = []

                for line in text.strip().split("\n"):
                    repo = parse_repo(line)
                    if repo and repo not in repos:
                        rel = get_latest(repo)
                        if rel and "tag_name" in rel:
                            repos[repo] = rel["tag_name"]
                            history.setdefault(repo, []).append(rel["tag_name"])
                            repos_added += 1
                            new_repos.append(repo)

                if repos_added:
                    save_repos(repos)
                    save_history(history)
                    update_badge(len(repos))
                    git_push_changes()
                    send_msg(chat_id,
                        f"✅ Added {repos_added} new repos:\n" + "\n".join([f"🔹 `{r}`" for r in new_repos]) +
                        f"\n\n📊 Total now: *{len(repos)}*"
                    )
                else:
                    send_msg(chat_id, "📭 No new valid repos found or all already tracked.")

        time.sleep(2)

if __name__ == "__main__":
    main()
