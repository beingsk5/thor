# main.py

import os, requests, json, time
from io import BytesIO
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
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    if reply_to: data["reply_to_message_id"] = reply_to
    if buttons: data["reply_markup"] = {"inline_keyboard": buttons}
    return requests.post(f"{API}/sendMessage", json=data, timeout=5).json()

def send_photo(chat_id, image_bytes, caption=None):
    files = {"photo": ("chart.png", image_bytes)}
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
    requests.post(f"{API}/sendPhoto", data=data, files=files, timeout=10)

def delete_msg(chat_id, msg_id):
    requests.post(f"{API}/deleteMessage", json={
        "chat_id": chat_id,
        "message_id": msg_id
    }, timeout=5)

def get_updates(offset=None):
    params = {"timeout": 30, "offset": offset} if offset else {"timeout": 30}
    return requests.get(f"{API}/getUpdates", params=params, timeout=5).json().get("result", [])

def parse_repo(text):
    if "github.com/" in text:
        parts = text.split("github.com/")[1].split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1].split()[0]}"
    return None

def get_latest(repo):
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}/releases/latest", timeout=5)
        return r.json() if r.status_code == 200 else None
    except:
        return None

def load_file(path):
    return json.load(open(path)) if os.path.exists(path) else {}

def save_file(data, path):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

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

def handle_command(chat_id, text):
    repos = load_file(REPOS_FILE)
    if text == "/start":
        send_msg(chat_id, "👋 Welcome! Send a GitHub repo link to track new releases.\nUse /list to see tracked repos, /remove to remove one.")
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

def main():
    offset = None
    repos = load_file(REPOS_FILE)

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
                    rel = get_latest(repo)
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
    main()
