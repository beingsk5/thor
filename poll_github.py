import os
import json
import requests
from datetime import datetime, timezone

TRACKED_FILE = 'data/tracked.json'
NOTIFIED_FILE = 'data/notified.json'
BADGE_FILE = 'badge/tracked-count.json'
BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHANNEL = os.environ['TELEGRAM_CHANNEL']

def send_telegram(text, btn_url=None):
    json_body = {
        'chat_id': CHANNEL,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': False
    }
    if btn_url:
        json_body['reply_markup'] = {
            'inline_keyboard': [[{'text': '⬇️ View release', 'url': btn_url}]]
        }
    requests.post(
        f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
        json=json_body
    )

def main():
    today = datetime.now(timezone.utc).date()
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
        # Date logic: skip releases before today, or if already notified
        rel_date = None
        if 'published_at' in latest:
            rel_date = datetime.fromisoformat(latest["published_at"].replace("Z", "+00:00")).date()
        if rel_date is None or rel_date < today:
            continue
        if str(latest['id']) != str(notified.get(repo, '')):
            # Beautiful notification
            notes = (latest.get("body") or '').replace('<', "&lt;").replace('>', "&gt;")
            note1 = (notes[:200] + "…") if notes and len(notes) > 200 else notes
            text = (
                f"🆕 <b>{repo}</b> just published a new release!<br>"
                f"<a href='{latest['html_url']}'><b>{latest['tag_name']}</b></a> "
                f"({rel_date.strftime('%Y-%m-%d')})<br>"
                f"{(latest.get('name', '') or '')}<br><br>"
                f"{note1}"
            )
            send_telegram(text, btn_url=latest["html_url"])
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
