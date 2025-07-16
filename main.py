import os, requests, json, time, re
import matplotlib.pyplot as plt

TOKEN = os.getenv("TELEGRAM_TOKEN")
OWNER_ID = int(os.getenv("TELEGRAM_OWNER_ID"))
API = f"https://api.telegram.org/bot{TOKEN}"
REPOS_FILE = "repos.json"
HISTORY_FILE = "history.json"
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

def get_latest(repo):
    r = requests.get(f"https://api.github.com/repos/{repo}/releases/latest")
    return r.json() if r.status_code == 200 else None

def load_repos():
    if os.path.exists(REPOS_FILE):
        with open(REPOS_FILE) as f:
            return json.load(f)
    fallback = os.getenv("TRACKED_REPOS", "")
    repos = {r.strip(): "" for r in fallback.split(",") if "/" in r}
    save_repos(repos)
    return repos

def save_repos(r):
    with open(REPOS_FILE, "w") as f:
        json.dump(r, f, indent=2)

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return {}

def save_history(h):
    with open(HISTORY_FILE, "w") as f:
        json.dump(h, f, indent=2)

def parse_repos(text):
    possible = re.findall(r"[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+", text)
    return list(set(possible))

def create_chart(history):
    counts = {repo: len(tags) for repo, tags in history.items()}
    if not counts:
        return None
    repos, totals = zip(*sorted(counts.items(), key=lambda x: -x[1])[:10])
    plt.figure(figsize=(8, 4))
    plt.barh(repos, totals, color="skyblue")
    plt.xlabel("Total Releases")
    plt.title("📊 Top Tracked Repos by Release Count")
    plt.gca().invert_yaxis()
    file = "chart.png"
    plt.tight_layout()
    plt.savefig(file)
    plt.close()
    return file

def handle_command(chat_id, text):
    repos = load_repos()
    history = load_history()

    if text == "/start":
        send_msg(chat_id, "👋 Welcome! Send a GitHub repo (or list) to start tracking.\nUse /help to view available commands.")
    elif text == "/help":
        send_msg(chat_id,
            "*Commands Available:*\n"
            "`/start` - Show welcome message\n"
            "`/help` - Show this help\n"
            "`/about` - About the bot\n"
            "`/ping` - Check bot status\n"
            "`/list` - View tracked repos\n"
            "`/releases` - Show latest release tags\n"
            "`/chart` - View bar chart of release activity\n"
            "`/clearall` - Remove all tracked repos\n"
            "`/remove owner/repo` - Remove a specific repo"
        )
    elif text == "/about":
        send_msg(chat_id, "🤖 *Im-Thor*: GitHub release tracker bot.\nTracks releases, sends updates, charts, and inline downloads.")
    elif text == "/ping":
        send_msg(chat_id, "🏓 Pong! Bot is alive.")
    elif text == "/list":
        if repos:
            lines = [f"🔹 `{r}`" for r in repos.keys()]
            send_msg(chat_id, "*Tracked Repositories:*\n" + "\n".join(lines))
        else:
            send_msg(chat_id, "📭 No repositories are being tracked.")
    elif text == "/releases":
        if repos:
            lines = [f"📦 `{r}` → `{v}`" if v else f"📦 `{r}` → _none yet_" for r, v in repos.items()]
            send_msg(chat_id, "*Latest Releases:*\n" + "\n".join(lines))
        else:
            send_msg(chat_id, "📭 No repositories are being tracked.")
    elif text == "/chart":
        chart = create_chart(history)
        if chart:
            with open(chart, "rb") as f:
                requests.post(f"{API}/sendPhoto", files={"photo": f}, data={"chat_id": chat_id})
        else:
            send_msg(chat_id, "📉 Not enough data to generate chart.")
    elif text == "/clearall":
        save_repos({})
        save_history({})
        send_msg(chat_id, "🧹 All tracked repositories cleared.")
    elif text.startswith("/remove"):
        parts = text.split()
        if len(parts) == 2 and parts[1] in repos:
            del repos[parts[1]]
            save_repos(repos)
            history.pop(parts[1], None)
            save_history(history)
            send_msg(chat_id, f"🗑️ Removed `{parts[1]}` from tracking.")
        else:
            send_msg(chat_id, "❌ Usage: `/remove owner/repo`")

def main():
    offset = None

    while True:
        for upd in get_updates(offset):
            offset = upd["update_id"] + 1

            if "message" in upd:
                msg = upd["message"]
                chat_id = msg["chat"]["id"]
                uid = msg["from"]["id"]
                text = msg.get("text", "").strip()
                msg_id = msg["message_id"]

                if uid != OWNER_ID:
                    send_msg(chat_id, "⛔ You are not authorized.")
                    continue

                if text.startswith("/"):
                    handle_command(chat_id, text)
                    continue

                # Auto parse multiple repos from message
                new_repos = parse_repos(text)
                repos = load_repos()
                history = load_history()
                added = 0

                for repo in new_repos:
                    if repo not in repos:
                        rel = get_latest(repo)
                        if rel and "tag_name" in rel:
                            repos[repo] = rel["tag_name"]
                            history.setdefault(repo, []).append(rel["tag_name"])
                            added += 1

                save_repos(repos)
                save_history(history)

                if added > 0:
                    send_msg(chat_id,
                        f"✅ Added *{added} new repos* to tracking.\n📊 Total now: *{len(repos)}*")
                else:
                    send_msg(chat_id, "📭 No new valid repos found or all already tracked.")

        time.sleep(2)

if __name__ == "__main__":
    main()
