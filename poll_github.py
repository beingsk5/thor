import os
import json
import requests
from datetime import datetime, timezone, timedelta

TRACKED_FILE = 'data/tracked.json'
NOTIFIED_FILE = 'data/notified.json'
BADGE_FILE = 'badge/tracked-count.json'
BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHANNEL = os.environ['TELEGRAM_CHANNEL']

def get_repo_name(full_repo):
    return full_repo.split("/")[-1]

def send_telegram_message(text, btn_url=None):
    json_body = {
        'chat_id': CHANNEL,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    if btn_url:
        json_body['reply_markup'] = {
            'inline_keyboard': [[{'text': '⬇️ View Release', 'url': btn_url}]]
        }
    requests.post(
        f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
        json=json_body
    )

def send_telegram_file(asset_url, filename, repo, tag):
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {'Authorization': f'token {token}'} if token else {}
    r = requests.get(asset_url, headers=headers, stream=True)
    file_data = r.content
    repo_only = get_repo_name(repo)
    caption = f"⬇️ {repo_only} {tag}"
    # Telegram only accepts files up to 49MB - silently skip larger
    if len(file_data) > 49_000_000:
        return False
    resp = requests.post(
        f'https://api.telegram.org/bot{BOT_TOKEN}/sendDocument',
        data={
            'chat_id': CHANNEL,
            'caption': caption,
            'parse_mode': 'HTML'
        },
        files={'document': (filename, file_data)}
    )
    return resp.ok

def main():
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)

    if not os.path.exists(TRACKED_FILE):
        print('No tracked.json! Exiting.')
        return

    tracked = json.load(open(TRACKED_FILE))
    notified = json.load(open(NOTIFIED_FILE)) if os.path.exists(NOTIFIED_FILE) else {}

    for repo in tracked.get('repos', []):
        url = f'https://api.github.com/repos/{repo}/releases'
        try:
            r = requests.get(url)
            if not r.ok:
                continue
            releases = r.json()
            if not releases:
                continue
            latest = releases[0]

            rel_date = None
            if 'published_at' in latest:
                try:
                    rel_date = datetime.fromisoformat(latest["published_at"].replace("Z", "+00:00")).date()
                except Exception:
                    continue

            # Only notify if published today or yesterday!
            if rel_date is None or rel_date < yesterday:
                continue

            if str(latest['id']) != str(notified.get(repo, '')):
                notes = (latest.get("body") or '').replace('<', "&lt;").replace('>', "&gt;")
                note1 = (notes[:300] + "…") if notes and len(notes) > 300 else notes
                repo_name = get_repo_name(repo)
                text = (
                    f"🆕 <b>{repo_name}</b> just published a new release!\n"
                    f"🔖 <b>{latest['tag_name']}</b> <code>({rel_date.strftime('%Y-%m-%d')})</code>\n"
                )
                if latest.get('name'):
                    text += f"\n🚀 <b>Release name:</b> {latest.get('name','')}\n"
                if note1:
                    text += f"\n📝 <b>Changelog:</b>\n{note1}\n"
                text += "\n⬇️ <b>Download below</b>:"
                send_telegram_message(text, btn_url=latest["html_url"])

                # Send all non-"source code" assets, skip large files silently
                for asset in latest.get("assets", []):
                    asset_name = (asset.get("name") or "").lower()
                    asset_label = (asset.get("label") or "").lower()
                    if "source code" in asset_name or "source code" in asset_label:
                        continue
                    send_telegram_file(
                        asset["browser_download_url"], asset["name"],
                        repo, latest["tag_name"]
                    )

                notified[repo] = str(latest['id'])
        except Exception as e:
            # Quiet operation: log errors locally!
            print(f"[ERROR] {repo}: {e}")

    with open(NOTIFIED_FILE, 'w') as f:
        json.dump(notified, f, indent=2)

    # badge update 
    os.makedirs('badge', exist_ok=True)
    with open(BADGE_FILE, 'w') as f:
        json.dump({
            'schemaVersion': 1,
            'label': 'tracked repos',
            'message': str(len(tracked.get('repos', []))),
            'color': 'brightgreen'
        }, f)

if __name__ == '__main__':
    main()
