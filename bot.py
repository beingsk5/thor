import os
import re
import json
import requests
from datetime import datetime, timezone
from io import BytesIO
from telegram import (
    Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
)
from flask import Flask
from threading import Thread
from base64 import b64encode, b64decode

# --- Flask keepalive for 24/7 uptime (Replit) ---
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "I'm alive!"

def run_flask():
    app_flask.run(host='0.0.0.0', port=8080)

Thread(target=run_flask).start()

# --- Config and constants ---
BOT_TOKEN = os.environ['BOT_TOKEN']
GITHUB_OWNER = os.environ['GITHUB_OWNER']
GITHUB_REPO = os.environ['GITHUB_REPO']
GITHUB_TOKEN = os.environ['GITHUB_TOKEN']
TELEGRAM_CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "@yourchannel")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456"))
DATA_PATH = "data/tracked.json"
RELEASES_DATA_PATH = "data/releases.json"
NOTIFIED_PATH = "data/notified.json"
RELEASES_PAGE_SIZE = 15

def github_headers():
    return {"Authorization": f"token {GITHUB_TOKEN}"}

def github_file_url(path):
    return f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"

def load_tracked():
    url = github_file_url(DATA_PATH)
    r = requests.get(url, headers=github_headers())
    if r.status_code == 404:
        return [], None
    r.raise_for_status()
    content = r.json()
    repos = []
    sha = content["sha"]
    try:
        data = json.loads(b64decode(content["content"] + '===').decode())
        repos = data.get("repos", [])
    except Exception:
        repos = []
    return repos, sha

def save_tracked(repos, sha):
    url = github_file_url(DATA_PATH)
    new_data = json.dumps({"repos": repos}, indent=2)
    payload = {
        "message": "Bot update tracked repos",
        "content": b64encode(new_data.encode()).decode(),
        "sha": sha
    }
    r = requests.put(url, headers=github_headers(), json=payload)
    r.raise_for_status()
    return r.json()['content']['sha']

def extract_repos_from_text(text):
    text = text.replace(',', ' ').replace('\n', ' ')
    pattern = r'(?:https?://github\.com/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)'
    found = re.findall(pattern, text)
    clean = set(f"{u}/{r}" for (u, r) in found)
    return clean

def validate_repo_exists(repo):
    url = f"https://api.github.com/repos/{repo}"
    headers = github_headers()
    resp = requests.get(url, headers=headers)
    if resp.ok:
        data = resp.json()
        if 'full_name' in data and data['full_name'] == repo:
            return True
    return False

def load_releases_data():
    url = github_file_url(RELEASES_DATA_PATH)
    r = requests.get(url, headers=github_headers())
    if r.status_code == 404:
        return []
    r.raise_for_status()
    content = r.json()
    try:
        data = json.loads(b64decode(content["content"] + '===').decode())
    except Exception:
        data = []
    return data if isinstance(data, list) else []

def load_notified():
    url = github_file_url(NOTIFIED_PATH)
    r = requests.get(url, headers=github_headers())
    if r.status_code == 404:
        return {}, None
    r.raise_for_status()
    content = r.json()
    try:
        data = json.loads(b64decode(content["content"] + '===').decode())
    except Exception:
        data = {}
    sha = content["sha"]
    return data, sha

def save_notified(notified, sha):
    url = github_file_url(NOTIFIED_PATH)
    new_data = json.dumps(notified, indent=2)
    payload = {
        "message": "Bot update notified.json (manual notify)",
        "content": b64encode(new_data.encode()).decode(),
        "sha": sha
    }
    r = requests.put(url, headers=github_headers(), json=payload)
    r.raise_for_status()
    return r.json()['content']['sha']

# --- Releases.json update helpers ---
def update_release_entry(repo):
    url = f"https://api.github.com/repos/{repo}/releases"
    try:
        r = requests.get(url)
        if not r.ok:
            entry = {"repo": repo, "tag": "none", "date": ""}
        else:
            releases = r.json()
            for rel in releases:
                if rel.get("draft") or rel.get("prerelease"):
                    continue
                tag = rel.get("tag_name", "")
                pub = rel.get("published_at", "")
                if tag and pub:
                    try:
                        rel_date = datetime.fromisoformat(pub.replace("Z", "+00:00")).date()
                        entry = {"repo": repo, "tag": tag, "date": rel_date.strftime("%Y-%m-%d")}
                        break
                    except Exception:
                        continue
            else:
                entry = {"repo": repo, "tag": "none", "date": ""}
    except Exception:
        entry = {"repo": repo, "tag": "none", "date": ""}

    url_rel = github_file_url(RELEASES_DATA_PATH)
    r_rel = requests.get(url_rel, headers=github_headers())
    if r_rel.status_code == 404:
        releases_data = []
        sha = None
    else:
        r_rel.raise_for_status()
        content_rel = r_rel.json()
        try:
            releases_data = json.loads(b64decode(content_rel["content"] + '===').decode())
        except Exception:
            releases_data = []
        sha = content_rel["sha"]
    releases_map = {r['repo']: r for r in releases_data if 'repo' in r}
    releases_map[repo] = entry
    new_data = list(releases_map.values())
    payload = {
        "message": f"Update releases.json for {repo}",
        "content": b64encode(json.dumps(new_data, indent=2).encode()).decode(),
        "sha": sha
    }
    requests.put(url_rel, headers=github_headers(), json=payload)

def remove_release_entry(repo):
    url_rel = github_file_url(RELEASES_DATA_PATH)
    r_rel = requests.get(url_rel, headers=github_headers())
    if r_rel.status_code == 404:
        releases_data = []
        sha = None
    else:
        r_rel.raise_for_status()
        content_rel = r_rel.json()
        try:
            releases_data = json.loads(b64decode(content_rel["content"] + '===').decode())
        except Exception:
            releases_data = []
        sha = content_rel["sha"]
    new_data = [r for r in releases_data if r['repo'] != repo]
    payload = {
        "message": f"Remove {repo} from releases.json",
        "content": b64encode(json.dumps(new_data, indent=2).encode()).decode(),
        "sha": sha
    }
    requests.put(url_rel, headers=github_headers(), json=payload)

# --- Helper: auto-delete in private chats ---
async def delete_trigger_message(update):
    if update.effective_chat.type == "private":
        try:
            await update.message.delete()
        except Exception:
            pass

# --- Bot Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_trigger_message(update)
    keyboard = [
        ["/add", "/remove", "/list", "/releases"],
        ["/about", "/help"]
    ]
    await update.message.reply_text(
        "👋 Hi! Paste GitHub repos or use /add /remove /list commands.\n"
        "Send multiple repos using space, comma, or newline.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_trigger_message(update)
    await update.message.reply_text(
        "/add <repo(s)> — Add repo(s)\n"
        "/remove <repo> — Remove repo\n"
        "/list — Show tracked repos\n"
        "/releases — Paginated release log (private chat only)\n"
        "/notify <repo> — Manually notify channel AND update notified.json\n"
        "/about — About\n"
        "/clearall — Clear all (admin)\n"
        "/ping — Check bot"
    )

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_trigger_message(update)
    await update.message.reply_text(
        "🦸 GitHub Release Tracker\n"
        "• Add repos or use commands\n"
        "• Persistent storage in your GitHub\n"
        "• Channel notifications"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_trigger_message(update)
    await update.message.reply_text("🏓 Bot is alive!")

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_trigger_message(update)
    if not context.args:
        await update.message.reply_text("Usage: /add <repo(s) or links>")
        return
    await process_repo_addition(update, " ".join(context.args))

async def remove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_trigger_message(update)
    if not context.args:
        await update.message.reply_text("Usage: /remove <repo>")
        return
    repos_to_remove = extract_repos_from_text(" ".join(context.args))
    if not repos_to_remove:
        await update.message.reply_text("No valid repositories recognized for removal.")
        return
    repos, sha = load_tracked()
    actually_removed, not_found = [], []
    for repo in repos_to_remove:
        if repo in repos:
            repos.remove(repo)
            actually_removed.append(repo)
        else:
            not_found.append(repo)
    if actually_removed:
        save_tracked(repos, sha)
        for repo in actually_removed:
            remove_release_entry(repo)
    msg = ""
    if actually_removed:
        msg += "❌ Removed:\n" + "\n".join(actually_removed)
    if not_found:
        msg += "\nℹ️ Not tracked:\n" + "\n".join(not_found)
    await update.message.reply_text(msg or "Nothing to remove.")

async def any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_trigger_message(update)
    if update.message.text.startswith('/'):
        return
    await process_repo_addition(update, update.message.text)

async def process_repo_addition(update, text):
    repos_to_check = extract_repos_from_text(text)
    if not repos_to_check:
        await update.message.reply_text(
            "❗ No valid repositories found. Use username/repo or GitHub repo link."
        )
        return
    if len(repos_to_check) > 20:
        await update.message.reply_text(
            "⚠️ Max 20 repos at a time. Please split the list."
        )
        return
    added, skipped, failed = [], [], []
    repos, sha = load_tracked()
    for repo in repos_to_check:
        if repo in repos:
            skipped.append(repo)
            continue
        try:
            if validate_repo_exists(repo):
                repos.append(repo)
                added.append(repo)
            else:
                failed.append(repo)
        except Exception as e:
            failed.append(f"{repo} (error: {str(e)})")
    if added:
        save_tracked(repos, sha)
        for repo in added:
            update_release_entry(repo)
    msg = ""
    if added:
        msg += "✅ Added:\n" + "\n".join(added)
    if skipped:
        msg += "\n⏭ Already tracking:\n" + "\n".join(skipped)
    if failed:
        msg += "\n❌ Invalid or inaccessible:\n" + "\n".join(failed)
    await update.message.reply_text(msg or "No new repositories added.")

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_trigger_message(update)
    repos, _ = load_tracked()
    if not repos:
        await update.message.reply_text("No repositories tracked.")
        return
    await update.message.reply_text(
        "📋 Tracked repos:\n" + "\n".join(f"- `{r}`" for r in repos), parse_mode="Markdown"
    )

async def releases_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_trigger_message(update)
    if update.effective_chat.type != "private":
        await update.message.reply_text("⚠️ /releases works only in your personal chat with the bot.")
        return
    releases_data = load_releases_data()
    if not releases_data:
        await update.message.reply_text("No releases are recorded yet. Wait for an update.")
        return
    releases_data.sort(key=lambda x: x.get("date") or "", reverse=True)
    chat_id = update.effective_chat.id
    context.bot_data[f'releases_list_{chat_id}'] = releases_data
    await show_releases_page(update, context, page=0)

async def show_releases_page(update, context, page=0):
    chat_id = update.effective_chat.id
    releases_data = context.bot_data.get(f'releases_list_{chat_id}', [])
    page_size = RELEASES_PAGE_SIZE
    total = len(releases_data)
    start = page * page_size
    end = min(start + page_size, total)
    subset = releases_data[start:end]
    msg = f"📦 Release History ({start+1}-{end}/{total})\n\n"
    if not subset:
        msg += "No releases recorded."
    else:
        for rel in subset:
            repo = rel.get("repo", "unknown/repo")
            tag = rel.get("tag", "?")
            date = rel.get("date", "?")
            msg += f"{repo} — {tag} ({date})\n"
    nav_buttons = []
    if start > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Back", callback_data=f"rel_page:{page-1}"))
    if end < total:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"rel_page:{page+1}"))
    reply_markup = InlineKeyboardMarkup([nav_buttons] if nav_buttons else [])
    if getattr(update, 'message', None):
        await update.message.reply_text(msg, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text(msg, parse_mode="HTML", reply_markup=reply_markup)

async def releases_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page_match = re.match(r'rel_page:(\d+)', query.data)
    page = int(page_match.group(1)) if page_match else 0
    await show_releases_page(update, context, page)

async def notify_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_trigger_message(update)
    if not context.args:
        await update.message.reply_text("Usage: /notify <repo>")
        return
    repo = context.args[0]
    repos, _ = load_tracked()
    if repo not in repos:
        await update.message.reply_text(f"{repo} is not tracked.")
        return
    r = requests.get(f"https://api.github.com/repos/{repo}/releases")
    if not r.ok:
        await update.message.reply_text("Failed to fetch releases.")
        return
    releases = r.json()
    latest = None
    for rel in releases:
        if rel.get("published_at") and rel.get("tag_name"):
            latest = rel
            break
    if latest is None:
        await update.message.reply_text("No valid releases found.")
        return
    repo_only = repo.split('/')[-1]
    tag = latest.get('tag_name', '')
    rel_date = datetime.fromisoformat(latest["published_at"].replace("Z", "+00:00")).strftime('%Y-%m-%d')
    notes = (latest.get("body") or '').replace('<', "&lt;").replace('>', "&gt;")
    note1 = (notes[:300] + "…") if notes and len(notes) > 300 else notes
    text = (
        f"🆕 <b>{repo}</b> just published a new release!\n"
        f"🔖 <b>{tag}</b> <code>({rel_date})</code>\n"
    )
    if latest.get('name'):
        text += f"\n🚀 <b>Release name:</b> {latest.get('name','')}\n"
    if note1:
        text += f"\n📝 <b>Changelog:</b>\n{note1}\n"
    text += "\n⬇️ <b>Download below</b>:"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("GitHub Repo", url=latest["html_url"])]])
    await context.bot.send_message(chat_id=TELEGRAM_CHANNEL, text=text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=reply_markup)
    for asset in latest.get("assets", []):
        asset_name = (asset.get("name") or "").lower()
        asset_label = (asset.get("label") or "").lower()
        if "source code" in asset_name or "source code" in asset_label:
            continue
        file_url = asset["browser_download_url"]
        caption = f"⬇️ {repo_only} {tag}"
        resp = requests.get(file_url)
        if resp.ok and len(resp.content) <= 49_000_000:
            file_bytes = BytesIO(resp.content)
            file_bytes.name = asset.get("name", "asset.bin")
            await context.bot.send_document(chat_id=TELEGRAM_CHANNEL, document=InputFile(file_bytes),
                                           caption=caption, parse_mode="HTML")
    # --- Update notified.json in GitHub! ---
    notified, sha = load_notified()
    if latest and tag and "id" in latest:
        notified[repo] = str(latest["id"])
        save_notified(notified, sha)
        update_release_entry(repo)

async def clearall_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_trigger_message(update)
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can clear all repos!")
        return
    _, sha = load_tracked()
    save_tracked([], sha)
    await update.message.reply_text("☑️ All repos cleared.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("remove", remove_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("releases", releases_cmd))
    app.add_handler(CommandHandler("notify", notify_cmd))
    app.add_handler(CommandHandler("clearall", clearall_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_message))
    app.add_handler(CallbackQueryHandler(releases_callback, pattern=r"rel_page:\d+"))
    app.run_polling()
