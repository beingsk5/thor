import os
import json
import requests

TRACKED_FILE = 'data/tracked.json'
NOTIFIED_FILE = 'data/notified.json'
BADGE_FILE = 'badge/tracked-count.json'
BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHANNEL = os.environ['TELEGRAM_CHANNEL']

def send_telegram(text, btn_url=None):
    json_body = {
        'chat_id': CHANNEL,
        'text': text,
        'parse_mode': 'Markdown',
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
        if str(latest['id']) != str(notified.get(repo, '')):
            text = f'🆕 *{repo}* released [{latest["tag_name"]}]({latest["html_url"]})\n{latest.get("name", "")[:40]}'
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
