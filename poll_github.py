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

def get_best_release(releases):
    """Return the most recent valid release (with tag_name and published_at)."""
    for rel in releases:
        tag = rel.get("tag_name", "")
        pub = rel.get("published_at", "")
        if tag and pub:
            try:
                rel_date = datetime.fromisoformat(pub.replace("Z", "+00:00")).date()
            except Exception:
                rel_date = None
            if rel_date:
                return tag, rel_date.strftime("%Y-%m-%d")
    return "none", ""

def fetch_latest_release(repo):
    url = f'https://api.github.com/repos/{repo}/releases'
    r = requests.get(url)
    if not r.ok:
        return {"repo": repo, "tag": "none", "date": ""}
    releases = r.json()
    tag, date_str = get_best_release(releases)
    return {"repo": repo, "tag": tag, "date": date_str}

def main():
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    tracked = load_json_or_default(TRACKED_FILE, {'repos': []})
    notified = load_json_or_default(NOTIFIED_FILE, {})
    all_releases = []

    # 1. Telegram notifications for new releases (unchanged)
    for repo in tracked.get('repos', []):
        url = f'https://api.github.com/repos/{repo}/releases'
        r = requests.get(url)
        if not r.ok:
            continue
        releases = r.json()
        # Use get_best_release on all releases, not just the first
        tag, rel_date_str = get_best_release(releases)
        latest = next((rel for rel in releases if rel.get("tag_name", "") == tag and rel.get("published_at", "")), None)

        # Only proceed if we found a valid release
        if latest and rel_date_str:
            rel_date = datetime.strptime(rel_date_str, "%Y-%m-%d").date()
            if rel_date is None or rel_date < yesterday:
                continue
            if str(latest['id']) != str(notified.get(repo, '')):
                notes = (latest.get("body") or '').replace('<', "&lt;").replace('>', "&gt;")
                note1 = (notes[:300] + "…") if notes and len(notes) > 300 else notes
                text = (
                    f"🆕 <b>{repo}</b> just published a new release!\n"
                    f"🔖 <b>{tag}</b> <code>({rel_date_str})</code>\n"
                )
                if latest.get('name'):
                    text += f"\n🚀 <b>Release name:</b> {latest.get('name','')}\n"
                if note1:
                    text += f"\n📝 <b>Changelog:</b>\n{note1}\n"
                text += "\n⬇️ <b>Download below</b>:"
                send_telegram_message(text, btn_url=latest["html_url"])

                repo_only = repo.split('/')[-1]
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

        # Keep a consistent log in releases.json for every repo (even if no releases)
        all_releases.append({
            "repo": repo,
            "tag": tag,
            "date": rel_date_str
        })

    save_json(NOTIFIED_FILE, notified)
    save_json(RELEASES_FILE, all_releases)

    # 3. Badge update (unchanged)
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
