import requests
import os
import json
import time

TOKEN = os.getenv("TELEGRAM_TOKEN")
OWNER_ID = int(os.getenv("TELEGRAM_OWNER_ID"))
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"
REPOS_FILE = "repos.json"
pending_confirmations = {}

def send_message(chat_id, text, reply_to=None, buttons=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    if buttons:
        payload["reply_markup"] = {
            "inline_keyboard": buttons
        }
    requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)

def get_updates(offset=None):
    url = f"{TELEGRAM_API}/getUpdates"
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    return requests.get(url, params=params).json().get("result", [])

def get_latest_release(repo):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    r = requests.get(url)
    return r.json() if r.status_code == 200 else None

def load_repos():
    return json.load(open(REPOS_FILE)) if os.path.exists(REPOS_FILE) else {}

def save_repos(data):
    with open(REPOS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def parse_repo_link(text):
    if "github.com/" in text:
        parts = text.split("github.com/")[1].strip().split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    return None

def main():
    offset = None
    repos = load_repos()

    while True:
        updates = get_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1

            # Only allow messages from the owner
            if "message" in update:
                msg = update["message"]
                chat_id = msg["chat"]["id"]
                user_id = msg["from"]["id"]
                message_id = msg["message_id"]
                text = msg.get("text", "")

                if user_id != OWNER_ID:
                    send_message(chat_id, "⛔ Only the owner can use this bot.")
                    continue

                repo = parse_repo_link(text)
                if repo:
                    pending_confirmations[chat_id] = repo
                    send_message(chat_id,
                        f"🧐 You sent: `{repo}`\nDo you want to track this repo's releases?",
                        reply_to=message_id,
                        buttons=[
                            [{"text": "✅ Yes", "callback_data": "confirm_add"}],
                            [{"text": "❌ No", "callback_data": "cancel"}]
                        ]
                    )

            if "callback_query" in update:
                callback = update["callback_query"]
                data = callback["data"]
                user_id = callback["from"]["id"]
                chat_id = callback["message"]["chat"]["id"]
                message_id = callback["message"]["message_id"]

                if user_id != OWNER_ID:
                    send_message(chat_id, "⛔ You are not authorized to confirm.")
                    continue

                if data == "confirm_add":
                    repo = pending_confirmations.get(chat_id)
                    if repo:
                        release = get_latest_release(repo)
                        if release:
                            repos[repo] = release["tag_name"]
                            save_repos(repos)
                            send_message(chat_id, f"✅ Tracking `{repo}` releases.")
                        else:
                            send_message(chat_id, f"❌ Could not fetch releases for `{repo}`.")
                elif data == "cancel":
                    send_message(chat_id, "❌ Cancelled.")

        time.sleep(5)

if __name__ == "__main__":
    main()
