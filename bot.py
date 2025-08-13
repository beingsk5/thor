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

BOT_TOKEN = os.environ['BOT_TOKEN']
GITHUB_OWNER = os.environ['GITHUB_OWNER']
GITHUB_REPO = os.environ['GITHUB_REPO']
GITHUB_TOKEN = os.environ['GITHUB_TOKEN']
CHANNEL = os.environ.get("CHANNEL", "@yourchannel")
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

# ... handlers for /start, /help, etc ...

async def releases_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text("⚠️ /releases works only in your personal chat with the bot.")
        return
    repos, _ = load_tracked()
    if not repos:
        await update.message.reply_text("No tracked repositories. Add some first.")
        return
    releases_info = []
    for repo in repos:
        url = f"https://api.github.com/repos/{repo}/releases"
        try:
            resp = requests.get(url)
            if not resp.ok:
                # Still append for every repo, even on API error
                releases_info.append((datetime.min.replace(tzinfo=timezone.utc), repo, None))
                continue
            releases = resp.json()
            # Find the latest actual release (ignore if only tags, drafts, or missing published_at)
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
    chat_id = update.effective_chat.id
    context.bot_data[f'releases_info_{chat_id}'] = releases_info
    await show_releases_page(update, context, page=0)

async def show_releases_page(update, context, page=0):
    chat_id = update.effective_chat.id
    releases_info = context.bot_data.get(f'releases_info_{chat_id}', [])
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
    await context.bot.send_message(chat_id=CHANNEL, text=text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=reply_markup)
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
            await context.bot.send_document(chat_id=CHANNEL, document=InputFile(file_bytes),
                                           caption=caption, parse_mode="HTML")


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
