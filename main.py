import os, requests, json, time
from io import BytesIO
import matplotlib.pyplot as plt

TOKEN = os.getenv("TELEGRAM_TOKEN")
OWNER_ID = int(os.getenv("TELEGRAM_OWNER_ID"))
API = f"https://api.telegram.org/bot{TOKEN}"
REPOS_FILE = "repos.json"
HISTORY_FILE = "history.json"
PENDING = {}

# ---------------------------------
# Safe functions
# ---------------------------------

def safe_get(url, timeout=10):
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        else:
            print(f"[HTTP Error] {url} → {r.status_code}")
    except Exception as e:
        print(f"[GET FAILED] {url} → {e}")
    return None

def send_msg(chat_id, text, reply_to=None, buttons=None):
    try:
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        if reply_to: data["reply_to_message_id"] = reply_to
        if buttons: data["reply_markup"] = {"inline_keyboard": buttons}
        return requests.post(f"{API}/sendMessage", json=data, timeout=10).json()
    except Exception as e:
        print(f"[SEND MSG ERROR] {e}")

def send_photo(chat_id, image_bytes, caption=None):
    try:
        files = {"photo": ("chart.png", image_bytes)}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
        requests.post(f"{API}/sendPhoto", data=data, files=files, timeout=20)
    except Exception as e:
        print(f"[SEND PHOTO ERROR] {e}")

def delete_msg(chat_id, msg_id):
    try:
        requests.post(f"{API}/deleteMessage", json={
            "chat_id": chat_id,
            "message_id": msg_id
        }, timeout=5)
    except:
        pass

def get_updates(offset=None):
    try:
        params = {"timeout": 30, "offset": offset} if offset else {"timeout": 30}
        return requests.get(f"{API}/getUpdates", params=params, timeout=40).json().get("result", [])
    except Exception as e:
        print(f"[UPDATES ERROR] {e}")
        return []

# ---------------------------------
# Repo storage and visualization
# ---------------------------------

def parse_repo(text):
    if "github.com/" in text:
        parts = text.split("github.com/")[1].split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1].split()[0]}"
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

def draw_chart(repos):
    history = load_file(HISTORY_FILE)
    labels = []
    counts = []

    for repo in repos:
        labels.append(repo)
        counts.append(len(history.get(repo, [])))

    if not labels:
        return None

    plt.figure(figsize=(10, 4))
    plt.bar(labels, counts, color='skyblue')
    plt.xticks(rotation=30, ha='right')
    plt.title("Release Count per Repo")
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    return buf

# ---------------------------------
# Command handling
# ---------------------------------

def handle_command(chat_id, text):
    repos = load_file(REPOS_FILE)
    if not repos:
        repos = load_repos_from_env()
        save_file(repos, REPOS_FILE)

    if text == "/start":
        send_msg(chat_id, "👋 Welcome! Send a GitHub repo link to track releases.\nUse /help to see all commands.")
    elif text == "/help":
        help_text = (
            "*🛠 Available Commands:*\n\n"
            "`/start` - Show welcome message\n"
            "`/help` - List all available commands\n"
            "`/list` - Show tracked repositories\n"
            "`/releases` - Latest release for each repo\n"
            "`/chart` - Chart of tracked repo activity\n"
            "`/remove owner/repo` - Stop tracking a repo\n"
            "`/clearall` - Remove all tracked repos\n"
            "`/ping` - Check if bot is alive\n"
            "`/about` - Bot and dev info"
        )
        send_msg(chat_id, help_text)
    elif text == "/about":
        send_msg(chat_id, "🤖 *I'm Thor — GitHub Release Notifier Bot!*\n\nBuilt by @yourusername using Python. I track repositories and notify you of new releases.")
    elif text == "/ping":
        send_msg(chat_id, "🏓 Pong!")
    elif text == "/clearall":
        save_file({}, REPOS_FILE)
        send_msg(chat_id, "🧹 Cleared all tracked repositories.")
    elif text == "/list":
        if repos:
            lines = [f"🔹 `{r}`" for r in repos.keys()]
            send_msg(chat_id, "*Tracked Repositories:*\n" + "\n".join(lines))
        else:
            send_msg(chat_id, "📭 No repositories are being tracked.")
    elif text == "/releases":
        if repos:
            lines = [f"📦 `{r}` → `{v}`" for r, v in repos.items()]
            send_msg(chat_id, "*Latest Releases:*\n" + "\n".join(lines))
        else:
            send_msg(chat_id, "📭 No tracked repositories.")
    elif text == "/chart":
        chart = draw_chart(repos)
        if chart:
            send_photo(chat_id, chart, caption="📈 Release History")
        else:
            send_msg(chat_id, "📉 No data available for chart.")
    elif text.startswith("/remove"):
        args = text.split()
        if len(args) != 2:
            send_msg(chat_id, "❌ Usage: `/remove owner/repo`")
            return
        repo = args[1]
        if repo in repos:
            del repos[repo]
            save_file(repos, REPOS_FILE)
            send_msg(chat_id, f"🗑️ Removed `{repo}` from tracking.")
        else:
            send_msg(chat_id, "❌ That repo isn’t being tracked.")

# ---------------------------------
# Bot main loop
# ---------------------------------

def main():
    offset = None
    repos = load_file(REPOS_FILE)
    if not repos:
        repos = load_repos_from_env()
        save_file(repos, REPOS_FILE)

    while True:
        updates = get_updates(offset)
        for upd in updates:
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

                repo = parse_repo(text)
                if repo:
                    PENDING[chat_id] = (repo, msg_id)
                    send_msg(chat_id,
                        f"🧐 You sent: `{repo}`\nTrack releases?",
                        reply_to=msg_id,
                        buttons=[
                            [{"text": "✅ Yes", "callback_data": "confirm"}],
                            [{"text": "❌ No", "callback_data": "cancel"}]
                        ]
                    )
                else:
                    send_msg(chat_id, "❌ Please send a valid GitHub repo link.")

            if "callback_query" in upd:
                cb = upd["callback_query"]
                uid = cb["from"]["id"]
                cid = cb["message"]["chat"]["id"]
                cb_mid = cb["message"]["message_id"]
                data = cb["data"]

                if uid != OWNER_ID:
                    send_msg(cid, "⛔ Not authorized.")
                    continue

                if cid not in PENDING:
                    send_msg(cid, "❌ No repo pending.")
                    continue

                repo, original_msg_id = PENDING.pop(cid)

                if data == "confirm":
                    rel = safe_get(f"https://api.github.com/repos/{repo}/releases/latest")
                    if rel and "tag_name" in rel:
                        repos[repo] = rel["tag_name"]
                        save_file(repos, REPOS_FILE)
                        send_msg(cid, f"✅ Now tracking `{repo}`.")
                    else:
                        send_msg(cid, f"❌ Could not fetch latest release.")
                else:
                    send_msg(cid, "❌ Cancelled.")

                delete_msg(cid, original_msg_id)
                delete_msg(cid, cb_mid)

        time.sleep(2)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[🔥 Bot crashed] {e}")
