import os, requests, json, time

TOKEN = os.getenv("TELEGRAM_TOKEN")
OWNER_ID = int(os.getenv("TELEGRAM_OWNER_ID"))
API = f"https://api.telegram.org/bot{TOKEN}"
REPOS_FILE = "repos.json"
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
    return None

def get_latest(repo):
    r = requests.get(f"https://api.github.com/repos/{repo}/releases/latest")
    return r.json() if r.status_code == 200 else None

def load_repos():
    return json.load(open(REPOS_FILE)) if os.path.exists(REPOS_FILE) else {}

def save_repos(r): 
    with open(REPOS_FILE, "w") as f: json.dump(r, f, indent=2)

def handle_command(chat_id, text):
    repos = load_repos()
    if text == "/start":
        send_msg(chat_id, "👋 Welcome! Send a GitHub repo link to track new releases.\nUse /list to see tracked repos, /remove to remove one.")
    elif text == "/list":
        if repos:
            lines = [f"🔹 `{r}`" for r in repos.keys()]
            send_msg(chat_id, "*Tracked Repositories:*\n" + "\n".join(lines))
        else:
            send_msg(chat_id, "📭 No repositories are being tracked.")
    elif text.startswith("/remove"):
        args = text.split()
        if len(args) != 2:
            send_msg(chat_id, "❌ Usage: `/remove owner/repo`")
            return
        repo = args[1]
        if repo in repos:
            del repos[repo]
            save_repos(repos)
            send_msg(chat_id, f"🗑️ Removed `{repo}` from tracking.")
        else:
            send_msg(chat_id, "❌ That repo isn’t being tracked.")

def main():
    offset = None
    repos = load_repos()

    while True:
        for upd in get_updates(offset):
            offset = upd["update_id"] + 1

            # Messages
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

            # Button Clicks
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
                    rel = get_latest(repo)
                    if rel:
                        repos[repo] = rel["tag_name"]
                        save_repos(repos)
                        send_msg(cid, f"✅ Now tracking `{repo}`.")
                    else:
                        send_msg(cid, f"❌ Could not fetch latest release.")
                else:
                    send_msg(cid, "❌ Cancelled.")

                delete_msg(cid, original_msg_id)
                delete_msg(cid, cb_mid)

        time.sleep(2)

if __name__ == "__main__":
    main()
