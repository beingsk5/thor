# check_releases.py
import os
import json
import requests
from datetime import datetime

REPO_FILE = "repos.json"
HISTORY_FILE = "history.json"
BADGE_FILE = "badges/tracked_count_badge.svg"

GITHUB_API = "https://api.github.com/repos/"

def load_json(file, fallback):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return fallback

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

def fetch_latest_release(repo):
    url = f"{GITHUB_API}{repo}/releases/latest"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None

def generate_badge(count):
    badge_svg = f'''
<svg xmlns="http://www.w3.org/2000/svg" width="180" height="20">
  <linearGradient id="b" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <mask id="a"><rect width="180" height="20" rx="3" fill="#fff"/></mask>
  <g mask="url(#a)">
    <rect width="120" height="20" fill="#555"/>
    <rect x="120" width="60" height="20" fill="#4c1"/>
    <rect width="180" height="20" fill="url(#b)"/>
  </g>
  <g fill="#fff" text-anchor="middle"
     font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="60" y="15" fill="#010101" fill-opacity=".3">Tracked Repos</text>
    <text x="60" y="14">Tracked Repos</text>
    <text x="150" y="15" fill="#010101" fill-opacity=".3">{count}</text>
    <text x="150" y="14">{count}</text>
  </g>
</svg>
'''
    os.makedirs("badges", exist_ok=True)
    with open(BADGE_FILE, "w") as f:
        f.write(badge_svg)

def main():
    repos = load_json(REPO_FILE, {"repos": []})
    history = load_json(HISTORY_FILE, {})

    for repo_entry in repos["repos"]:
        repo = repo_entry["name"]
        data = fetch_latest_release(repo)
        if data and "tag_name" in data:
            tag = data["tag_name"]
            published = data.get("published_at", datetime.utcnow().isoformat())
            if repo not in history:
                history[repo] = []
            if not any(r["tag_name"] == tag for r in history[repo]):
                history[repo].insert(0, {"tag_name": tag, "published_at": published})

    save_json(HISTORY_FILE, history)
    generate_badge(len(repos["repos"]))

if __name__ == "__main__":
    main()
