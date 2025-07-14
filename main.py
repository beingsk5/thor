import requests
import os
import json
import time

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # For simplicity, one user only

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
REPOS_FILE = "repos.json"

def send_message(text, reply_to=None, buttons=None):
    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_to:
        data["reply_to_message_id"] = reply_to
    if buttons:
        data["reply_markup"] = {
            "inline_keyboard": buttons
        }
    requests.post(f"{TELEGRAM_API}/sendMessage", json=data)

def get_updates(offset=None):
    url = f"{TELEGRAM_API}/getUpdates"
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    response = requests.get(url, params=params)
    return response.json()["result"]

def get_latest_release(repo):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None

def load_repos():
    if os.path.exists(REPOS_FILE):
        with open(REPOS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_repos(repos):
    with open(REPOS_FILE, "w") as f:
        json.dump(repos, f, indent=2)

def parse_repo_link(text):
    if "github.com/" in text:
        parts = text.split("github.com/")[1].strip().split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    return None

def main():
    last_update_id = None
    pending_confirmations = {}
    repos = load_repos()

    while True:
        updates = get_updates(last_update_id)
        for update in updates:
            last_update_id = update["update_id"] + 1

            if "message" not in update:
                continue

            msg = update["message"]
            text = msg.get("text", "")
            message_id = msg["message_id"]

            if "/start" in text:
                send_message("👋 Send me a GitHub repo link to start tracking releases!", message_id)
                continue

            repo = parse_repo_link(text)
            if repo:
                # Ask for confirmation
                pending_confirmations[CHAT_ID] = repo
                send_message(f"🧐 You sent: `{repo}`\n\nDo you want to track this repo's releases?",
                             message_id,
                             buttons=[
                                 [{"text": "✅ Yes", "callback_data": "confirm_add"}],
                                 [{"text": "❌ No", "callback_data": "cancel"}]
                             ])
            else:
                send_message("❌ Invalid GitHub repo link. Please send a full repo link like:\n`https://github.com/owner/repo`", message_id)

        # Check for callback queries (confirmation)
        updates = get_updates(last_update_id)
        for update in updates:
            last_update_id = update["update_id"] + 1

            if "callback_query" in update:
                callback = update["callback_query"]
                data = callback["data"]
                msg = callback["message"]
                message_id = msg["message_id"]

                if data == "confirm_add":
                    repo = pending_confirmations.get(CHAT_ID)
                    if repo:
                        release = get_latest_release(repo)
                        if release:
                            repos[repo] = release["tag_name"]
                            save_repos(repos)
                            send_message(f"✅ Now tracking *{repo}* releases!", message_id)
                        else:
                            send_message("⚠️ Failed to fetch latest release. Check the repo exists or has releases.", message_id)
                    else:
                        send_message("Something went wrong. Please try again.", message_id)
                elif data == "cancel":
                    send_message("❌ Cancelled.", message_id)

        time.sleep(5)  # prevent spamming the Telegram API

if __name__ == "__main__":
    main()
