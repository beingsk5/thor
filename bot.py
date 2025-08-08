import os
import re
import json
import requests
from datetime import datetime, timezone
import matplotlib.pyplot as plt
from io import BytesIO
from telegram import (
    Update, ReplyKeyboardMarkup, InputFile,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
)

BOT_TOKEN = os.environ['BOT_TOKEN']
GITHUB_OWNER = os.environ['GITHUB_OWNER']
GITHUB_REPO = os.environ['GITHUB_REPO']
GITHUB_TOKEN = os.environ['GITHUB_TOKEN']
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456"))
DATA_PATH = "data/tracked.json"
RELEASES_PAGE_SIZE = 15

def github_headers():
    return {"Authorization": f"token {GITHUB_TOKEN}"}

def github_file_url():
    return f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{DATA_PATH}"

def load_tracked():
    url = github_file_url()
    r = requests.get(url, headers=github_headers())
    if r.status_code == 404:
        return [], None
    r.raise_for_status()
    content = r.json()
    from base64 import b64decode
    data = json.loads(b64decode(content["content"] + '===').decode())
    sha = content["sha"]
    return data.get("repos", []), sha

def save_tracked(repos, sha):
    url = github_file_url()
    from base64 import b64encode
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
    r = requests.get(url)
    return r.ok

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["/add", "/remove", "/list", "/releases"],
        ["/chart", "/about", "/help"]
    ]
    await update.message.reply_text(
        "👋 Hi! Paste GitHub repos or use /add /remove /list /chart commands.\n"
        "Send multiple repos using space, comma, or newline.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/add <repo(s)> — Add one or more repos (url or username/repo)\n"
        "/remove <repo> — Remove a tracked repo\n"
        "/list — Show tracked repos\n"
        "/releases — Show recent releases (paged, newest to oldest)\n"
        "/notify <repo> — Notify channel about latest release\n"
        "/chart — Release chart\n"
        "/about — About\n"
        "/clearall — Clear all (admin)\n"
        "/ping — Check bot is alive"
    )

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🦸 GitHub Release Tracker\n"
        "• Paste repos or use commands\n"
        "• Persistent storage in your GitHub\n"
        "• Channel notifications via GitHub Actions"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Bot is alive!")

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /add <repo(s) or links>")
        return
    await process_repo_addition(update, " ".join(context.args))

async def remove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /remove <repo or link>")
        return
    repos_to_remove = extract_repos_from_text(" ".join(context.args))
    if not repos_to_remove:
        await update.message.reply_text("No valid repositories recognized for removal. Please check the format (username/repo or link).")
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
    msg = ""
    if actually_removed:
        msg += "❌ Removed:\n" + "\n".join(actually_removed)
    if not_found:
        msg += "\nℹ️ Not tracked:\n" + "\n".join(not_found)
    await update.message.reply_text(msg or "Nothing to remove.")

async def any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith('/'):
        return
    await process_repo_addition(update, update.message.text)

async def process_repo_addition(update, text):
    repos_to_check = extract_repos_from_text(text)
    if not repos_to_check:
        await update.message.reply_text(
            "❗ No valid repositories found. Please use the format username/repo or paste a full GitHub repo link."
        )
        return
    if len(repos_to_check) > 20:
        await update.message.reply_text(
            "⚠️ Too many repos in one message (max 20 at a time). Please send in smaller batches."
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
    msg = ""
    if added:
        msg += "✅ Added:\n" + "\n".join(added)
    if skipped:
        msg += "\n⏭ Already tracking:\n" + "\n".join(skipped)
    if failed:
        msg += "\n❌ Invalid or inaccessible:\n" + "\n".join(failed)
    await update.message.reply_text(msg or "No new repositories added.")

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    repos, _ = load_tracked()
    if not repos:
        await update.message.reply_text("No repositories currently tracked.")
        return
    await update.message.reply_text(
        "📋 Tracked repos:\n" + "\n".join(f"- `{r}`" for r in repos), parse_mode="Markdown"
    )

async def releases_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    repos, _ = load_tracked()
    if not repos:
        await update.message.reply_text("No tracked repositories. Add some first.")
        return
    # Build and cache all releases info for paging
    releases_info = []
    for repo in repos:
        url = f"https://api.github.com/repos/{repo}/releases"
        try:
            resp = requests.get(url)
            if not resp.ok:
                releases_info.append((datetime.min.replace(tzinfo=timezone.utc), repo, None))
                continue
            releases = resp.json()
            found_release = None
            for rel in releases:
                if rel.get("published_at") and rel.get("tag_name"):
                    found_release = rel
                    break
            if found_release:
                rel_date = datetime.fromisoformat(found_release["published_at"].replace("Z", "+00:00"))
                releases_info.append((rel_date, repo, found_release))
            else:
                releases_info.append((datetime.min.replace(tzinfo=timezone.utc), repo, None))
        except Exception:
            releases_info.append((datetime.min.replace(tzinfo=timezone.utc), repo, None))

    releases_info.sort(reverse=True, key=lambda x: x[0])
    context.user_data['releases_info'] = releases_info
    await show_releases_page(update, context, page=0)

async def show_releases_page(update, context, page=0):
    releases_info = context.user_data.get('releases_info', [])
    page_size = RELEASES_PAGE_SIZE
    total = len(releases_info)
    start = page * page_size
    end = min(start + page_size, total)
    subset = releases_info[start:end]

    msg = f"📦 <b>Latest releases ({start+1}-{end}/{total})</b>\n\n"
    for rel_date, repo, rel in subset:
        if not rel or rel_date == datetime.min.replace(tzinfo=timezone.utc):
            msg += f"🔸 {repo}: <i>No actual releases found.</i>\n"
        else:
            date_str = rel_date.strftime('%Y-%m-%d')
            msg += f"🔹 <b>{repo}</b>: <code>{rel['tag_name']}</code> ({date_str})\n"
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
    if not context.args:
        await update.message.reply_text("Usage: /notify <repo>")
        return
    repo = context.args[0]
    repos, _ = load_tracked()
    if repo not in repos:
        await update.message.reply_text(f"{repo} is not currently tracked.")
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
    notes = (latest.get("body") or '').replace('<', "&lt;").replace('>', "&gt;")
    note1 = (notes[:300] + "…") if notes and len(notes) > 300 else notes
    rel_date = datetime.fromisoformat(latest["published_at"].replace("Z", "+00:00")).strftime('%Y-%m-%d')
    text = (
        f"🆕 <b>{repo}</b> just published a new release!\n"
        f"🔖 <b>{tag}</b> <code>({rel_date})</code>\n"
    )
    if latest.get('name'):
        text += f"\n🚀 <b>Release name:</b> {latest.get('name','')}\n"
    if note1:
        text += f"\n📝 <b>Changelog:</b>\n{note1}\n"
    text += "\n⬇️ <b>Download below</b>:"
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)
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
            await update.message.reply_document(document=InputFile(file_bytes), caption=caption, parse_mode="HTML")

async def clearall_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can clear all repos!")
        return
    _, sha = load_tracked()
    save_tracked([], sha)
    await update.message.reply_text("☑️ All repos cleared.")

async def chart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    repos, _ = load_tracked()
    if not repos:
        await update.message.reply_text("No repos tracked for chart.")
        return
    release_counts = {}
    for repo in repos:
        url = f"https://api.github.com/repos/{repo}/releases"
        releases = []
        try:
            resp = requests.get(url)
            if resp.ok:
                releases = resp.json()
        except Exception:
            continue
        months = [r.get("published_at", "")[:7] for r in releases if "published_at" in r]
        for month in months:
            if month:
                release_counts[month] = release_counts.get(month, 0) + 1
    if not release_counts:
        await update.message.reply_text("No release history yet.")
        return
    months = sorted(release_counts)
    values = [release_counts[m] for m in months]
    plt.figure(figsize=(6,3))
    plt.bar(months, values)
    plt.xticks(rotation=30, ha='right')
    plt.title("Releases per Month")
    plt.tight_layout()
    chart_img = BytesIO()
    plt.savefig(chart_img, format='png')
    chart_img.seek(0)
    await update.message.reply_photo(photo=InputFile(chart_img, filename="releases.png"))

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
    app.add_handler(CommandHandler("chart", chart_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_message))
    app.add_handler(CallbackQueryHandler(releases_callback, pattern=r"rel_page:\d+"))
    app.run_polling()
