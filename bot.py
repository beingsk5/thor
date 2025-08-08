import os
import re
import json
import requests
from datetime import datetime, timezone
import matplotlib.pyplot as plt
from io import BytesIO
from telegram import Update, ReplyKeyboardMarkup, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
)

BOT_TOKEN = os.environ['BOT_TOKEN']
GITHUB_OWNER = os.environ['GITHUB_OWNER']
GITHUB_REPO = os.environ['GITHUB_REPO']
GITHUB_TOKEN = os.environ['GITHUB_TOKEN']
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456"))
DATA_PATH = "data/tracked.json"

RELEASES_PAGE_SIZE = 15  # Keep page size reasonable for Telegram message limit

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

# Existing functions like save_tracked, validate_repo_exists, etc remain unchanged...

async def releases_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    repos, _ = load_tracked()
    if not repos:
        await update.message.reply_text("No tracked repositories. Add some first.")
        return
    # Save repos in context for callbacks
    context.user_data['release_repos'] = repos
    await show_releases_page(update, context, page=0)

async def show_releases_page(update, context, page=0):
    repos = context.user_data.get('release_repos')
    if not repos:
        repos, _ = load_tracked()
    releases_info = []
    for repo in repos:
        resp = requests.get(f"https://api.github.com/repos/{repo}/releases")
        releases = resp.json() if resp.ok else []
        if releases:
            rel = releases[0]
            rel_date = datetime.fromisoformat(rel["published_at"].replace("Z", "+00:00"))
            releases_info.append((rel_date, repo, rel))
        else:
            releases_info.append((datetime.min.replace(tzinfo=timezone.utc), repo, None))
    # Sort by date, newest first
    releases_info.sort(reverse=True, key=lambda x: x[0])

    page_size = RELEASES_PAGE_SIZE
    total = len(releases_info)
    start = page * page_size
    end = min(start + page_size, total)
    subset = releases_info[start:end]

    msg = f"📦 <b>Latest releases ({start+1}-{end}/{total})</b>\n\n"
    for rel_date, repo, rel in subset:
        if not rel:
            msg += f"🔸 {repo}: No releases found.\n"
        else:
            date_str = rel_date.strftime('%Y-%m-%d')
            msg += f"🔹 <b>{repo}</b>: <code>{rel['tag_name']}</code> ({date_str})\n"
    # Navigation buttons
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

# --- Existing command and handler registration ---

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
    # Paginated releases with inline buttons!
    app.add_handler(CallbackQueryHandler(releases_callback, pattern=r"rel_page:\d+"))
    app.run_polling()
