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

def get_latest_valid_release(repo):
    url = f'https://api.github.com/repos/{repo}/releases'
    try:
        r = requests.get(url)
        if not r.ok:
            return {"repo": repo, "tag": "none", "date": ""}
        releases = r.json()
        for rel in releases:
            if rel.get("draft") or rel.get("prerelease"):
                continue
            tag = rel.get("tag_name", "")
            pub = rel.get("published_at", "")
            if tag and pub:
                try:
                    rel_date = datetime.fromisoformat(pub.replace("Z", "+00:00")).date()
                    return {"repo": repo, "tag": tag, "date": rel_date.strftime("%Y-%m-%d")}
                except Exception:
                    continue
        return {"repo": repo, "tag": "none", "date": ""}
    except Exception:
        return {"repo": repo, "tag": "none", "date": ""}

def update_release_entry(repo):
    # Update/add one repo's entry in releases.json
    releases_data = load_json_or_default(RELEASES_FILE, [])
    releases_map = {r['repo']: r for r in releases_data}
    entry = get_latest_valid_release(repo)
    releases_map[repo] = entry
    new_data = list(releases_map.values())
    save_json(RELEASES_FILE, new_data)

def remove_release_entry(repo):
    releases_data = load_json_or_default(RELEASES_FILE, [])
    new_data = [r for r in releases_data if r['repo'] != repo]
    save_json(RELEASES_FILE, new_data)

def main():
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    tracked = load_json_or_default(TRACKED_FILE, {'repos': []})['repos']
    notified = load_json_or_default(NOTIFIED_FILE, {})
    releases_data = load_json_or_default(RELEASES_FILE, [])

    # Detect additions/removals
    releases_repos = {r['repo'] for r in releases_data}
    tracked_set = set(tracked)

    # Add newly tracked repos to releases.json
    repos_to_add = tracked_set - releases_repos
    for repo in repos_to_add:
        update_release_entry(repo)

    # Remove deleted repos from releases.json
    repos_to_remove = releases_repos - tracked_set
    for repo in repos_to_remove:
        remove_release_entry(repo)

    # Check for new releases for tracked repos
    for repo in tracked:
        url = f'https://api.github.com/repos/{repo}/releases'
        try:
            r = requests.get(url)
            if not r.ok:
                releases = []
            else:
                releases = r.json()
        except Exception:
            releases = []

        tag, rel_date_str, latest = None, None, None
        for rel in releases:
            if rel.get('draft') or rel.get('prerelease'):
                continue
            t = rel.get("tag_name", "")
            pub = rel.get("published_at", "")
            if t and pub:
                try:
                    rd = datetime.fromisoformat(pub.replace("Z", "+00:00")).date()
                    tag, rel_date_str, latest = t, rd.strftime("%Y-%m-%d"), rel
                    break
                except Exception:
                    continue

        if latest and rel_date_str:
            rel_date = datetime.strptime(rel_date_str, "%Y-%m-%d").date()
            if rel_date >= yesterday:
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
                    # Only update this repo's entry for new release
                    update_release_entry(repo)

    save_json(NOTIFIED_FILE, notified)

    # Badge update
    os.makedirs('badge', exist_ok=True)
    with open(BADGE_FILE, 'w') as f:
        json.dump({
            'schemaVersion': 1,
            'label': 'tracked repos',
            'message': str(len(tracked)),
            'color': 'brightgreen'
        }, f)

if __name__ == '__main__':
    main()
