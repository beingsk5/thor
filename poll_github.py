import os
import json
import requests
from datetime import datetime, timezone, timedelta

TRACKED_FILE = 'data/tracked.json'
NOTIFIED_FILE = 'data/notified.json'
BADGE_FILE = 'badge/tracked-count.json'
RELEASES_FILE = 'data/releases.json'
BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHANNEL = os.environ['TELEGRAM_CHANNEL']
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

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

def send_telegram_file(asset_url, filename, caption=""):
    headers = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}
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

def load_json_or_default(file_path, default):
    if os.path.exists(file_path):
        try:
            return json.load(open(file_path))
        except Exception:
            return default
    else:
        return default

def save_json(file_path, obj):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w') as f:
        json.dump(obj, f, indent=2)

def fetch_latest_release(repo):
    url = f'https://api.github.com/repos/{repo}/releases'
    r = requests.get(url)
    if not r.ok:
        return {"repo": repo, "tag": "none", "date": ""}
    releases = r.json()
    for rel in releases:
        if rel.get("published_at") and rel.get("tag_name"):
            rel_date = datetime.fromisoformat(rel["published_at"].replace("Z", "+00:00")).date()
            return {
                "repo": repo,
                "tag": rel.get("tag_name"),
                "date": rel_date.strftime("%Y-%m-%d")
            }
    # No releases, fallback
    return {"repo": repo, "tag": "none", "date": ""}

def main():
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    tracked = load_json_or_default(TRACKED_FILE, {'repos': []})
    notified = load_json_or_default(NOTIFIED_FILE, {})
    releases_list = load_json_or_default(RELEASES_FILE, [])

    # 1. Notification and asset logic
    for repo in tracked.get('repos', []):
        url = f'https://api.github.com/repos/{repo}/releases'
        r = requests.get(url)
        if not r.ok:
            continue
        releases = r.json()
        if not releases:
            continue
        latest = releases[0]
        rel_date = None
        if 'published_at' in latest:
            rel_date = datetime.fromisoformat(latest["published_at"].replace("Z", "+00:00")).date()
        if rel_date is None or rel_date < yesterday:
            continue
        if str(latest['id']) != str(notified.get(repo, '')):
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

            repo_only = repo.split('/')[-1]
            tag = str(latest['tag_name'])
            for asset in latest.get("assets", []):
                asset_name = (asset.get("name") or "").lower()
                asset_label = (asset.get("label") or "").lower()
                if "source code" in asset_name or "source code" in asset_label:
                    continue
                caption = f"⬇️ {repo_only} {tag}"
                send_telegram_file(
                    asset["browser_download_url"], asset["name"], caption=caption
                )
            notified[repo] = str(latest['id'])

    save_json(NOTIFIED_FILE, notified)

    # 2. releases.json update: scan EVERY tracked repo and update latest (always up-to-date, NO mixing notification logic)
    all_releases = []
    for repo in tracked.get('repos', []):
        latest_entry = fetch_latest_release(repo)
        all_releases.append(latest_entry)
    save_json(RELEASES_FILE, all_releases)

    # 3. Badge update
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
