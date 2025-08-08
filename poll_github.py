import os
import json
import requests
from datetime import datetime, timezone, timedelta

TRACKED_FILE = 'data/tracked.json'
NOTIFIED_FILE = 'data/notified.json'
BADGE_FILE = 'badge/tracked-count.json'
BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHANNEL = os.environ['TELEGRAM_CHANNEL']

def send_telegram_message(text, btn_url=None):
    json_body = {
        'chat_id': CHANNEL,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': False
    }
    if btn_url:
        json_body['reply_markup'] = {
            'inline_keyboard': [[{'text': '⬇️ View Release', 'url': btn_url}]]
        }
    requests.post(
        f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
        json=json_body
    )

def send_telegram_file(asset_url, filename, caption=""):
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {'Authorization': f'token {token}'} if token else {}
    r = requests.get(asset_url, headers=headers, stream=True)
    file_data = r.content
    if len(file_data) > 49_000_000:
        return False  # file too large
    resp = requests.post(
        f'https://api.telegram.org/bot{BOT_TOKEN}/sendDocument',
        data={
            'chat_id': CHANNEL,
            'caption': caption or filename,
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
        r = requests.get(url)
        if not r.ok:
            continue
        releases = r.json()
        if not releases:
            continue
        latest = releases[0]
        # Notify only for today/yesterday published releases
        rel_date = None
        if 'published_at' in latest:
            rel_date = datetime.fromisoformat(latest["published_at"].replace("Z", "+00:00")).date()
        if rel_date is None or rel_date < yesterday:
            continue
        if str(latest['id']) != str(notified.get(repo, '')):
            # Prepare the formatted message
            notes = (latest.get("body") or '').replace('<', "&lt;").replace('>', "&gt;")
            note1 = (notes[:300] + "…") if notes and len(notes) > 300 else notes
            text = (
                f"🆕 <b>{repo}</b> just published a new release!\n"
                f"🔖 <b>{latest['tag_name']}</b> <code>({rel_date.strftime('%Y-%m-%d')})</code>\n"
            )
            if latest.get('name'):
                text += f"\n🚀 <b>Release name:</b> {latest.get('name','')}\n"
            if note1:
                text += f"\n📝 <b>Changelog:</b>\n{note1}\n"
            text += "\n⬇️ <b>Download below</b>:"
            send_telegram_message(text, btn_url=latest["html_url"])

            # Send all non-"source code" assets as files with the custom caption
            repo_only = repo.split('/')[-1]
            tag = str(latest['tag_name'])
            for asset in latest.get("assets", []):
                asset_name = (asset.get("name") or "").lower()
                asset_label = (asset.get("label") or "").lower()
                if "source code" in asset_name or "source code" in asset_label:
                    continue
                # Space between repo and tag, as requested:
                caption = f"⬇️ {repo_only} {tag}"
                send_telegram_file(
                    asset["browser_download_url"], asset["name"], caption=caption
                )
            notified[repo] = str(latest['id'])
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
