import os
import json
import asyncio
import re
import aiohttp
from datetime import datetime, timezone
from io import BytesIO
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardRemove, ReplyKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)

TRACKED_FILE = 'data/tracked.json'
CHANNEL = os.environ['TELEGRAM_CHANNEL']
BOT_TOKEN = os.environ['BOT_TOKEN']
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')

RELEASES_PAGE_SIZE = 15   # Adjust as desired

def get_repo_name(input_str):
    m = re.search(r'([\w-]+)/([\w\-.]+)', input_str)
    return m.group(0) if m else None

def just_repo(repo):
    return repo.split("/")[-1]

def strip_extension(filename):
    return '.'.join(filename.split('.')[:-1]) if '.' in filename else filename

def load_tracked():
    try:
        with open(TRACKED_FILE) as f:
            return json.load(f).get("repos", [])
    except Exception:
        return []

def save_tracked(tracked):
    os.makedirs(os.path.dirname(TRACKED_FILE), exist_ok=True)
    with open(TRACKED_FILE, "w") as f:
        json.dump({"repos": tracked}, f, indent=2)

async def fetch_latest_release(session, repo):
    url = f'https://api.github.com/repos/{repo}/releases'
    headers = {'Accept': 'application/vnd.github+json'}
    if GITHUB_TOKEN:
        headers['Authorization'] = f'token {GITHUB_TOKEN}'
    async with session.get(url, headers=headers, timeout=10) as resp:
        if resp.status != 200:
            return None
        releases = await resp.json()
        if releases:
            return releases[0]
        return None

# Channel notification with proper file sending & debug
async def send_channel_notification(context, release, repo, notify_assets=True):
    tag = release['tag_name']
    date_str = (datetime.fromisoformat(release["published_at"].replace("Z", "+00:00")).strftime('%Y-%m-%d')) if 'published_at' in release else ''
    changelog = (release.get('body') or '').replace('<', '&lt;').replace('>', '&gt;')
    changelog = (changelog[:300] + "…") if len(changelog) > 300 else changelog
    name = release.get("name") or ""
    repo_only = just_repo(repo)
    msg = (
        f"🆕 <b>{repo_only}</b> just published a new release!\n"
        f"🔖 <b>{tag}</b> <code>({date_str})</code>\n"
    )
    if name:
        msg += f"\n🚀 <b>Release name:</b> {name}\n"
    if changelog:
        msg += f"\n📝 <b>Changelog:</b>\n{changelog}\n"
    msg += "\n⬇️ <b>Download below</b>:"
    await context.bot.send_message(
        chat_id=CHANNEL,
        text=msg,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬇️ View Release", url=release['html_url'])]
        ])
    )
    if notify_assets:
        for asset in release.get("assets", []):
            aname = (asset.get("name") or "").lower()
            alabel = (asset.get("label") or "").lower()
            print(f"[DEBUG] Found asset: {asset.get('name')}")
            if "source code" in aname or "source code" in alabel:
                print(f"[DEBUG] Skipped 'source code' asset: {asset.get('name')}")
                continue
            clean_name = strip_extension(asset.get("name") or "")
            caption = f"⬇️ <b>{clean_name}</b> from <b>{repo_only}</b> {release['tag_name']}"
            headers = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(asset["browser_download_url"], headers=headers) as r:
                        file_bytes = await r.read()
                if len(file_bytes) > 49_000_000:
                    print(f"[DEBUG] Skipping {asset.get('name')} (too large for Telegram upload)")
                    continue
                await context.bot.send_document(
                    chat_id=CHANNEL,
                    document=(BytesIO(file_bytes), asset.get("name")),
                    caption=caption,
                    parse_mode="HTML"
                )
                print(f"[DEBUG] Uploaded asset: {asset.get('name')}")
            except Exception as e:
                print(f"[ERROR] Failed to upload {asset.get('name')} : {str(e)}")
                await context.bot.send_message(chat_id=CHANNEL, text=f"Failed to send `{asset.get('name')}`: {e}")

async def handle_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = message.text.strip()
    repo = get_repo_name(text)
    if not repo:
        return
    tracked = load_tracked()
    try:
        if repo in tracked:
            notice = await message.reply_text(
                "Already tracking this repo!", quote=True)
            await asyncio.sleep(1)
            await message.delete()
            await notice.delete()
            return
        tracked.append(repo)
        save_tracked(tracked)
        notice = await message.reply_text(
            f"Started tracking <b>{repo}</b>.", parse_mode="HTML", quote=True)
        await asyncio.sleep(1)
        await message.delete()
        await notice.delete()
        return
    except Exception:
        pass

async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /add user/repo")
        return
    update.message.text = " ".join(context.args)
    await handle_add(update, context)

async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /remove user/repo")
        return
    repo = get_repo_name(" ".join(context.args))
    if not repo:
        await update.message.reply_text("Please provide a valid user/repo")
        return
    tracked = load_tracked()
    if repo in tracked:
        tracked.remove(repo)
        save_tracked(tracked)
        await update.message.reply_text(f"Removed <b>{repo}</b> from tracking.", parse_mode="HTML")
    else:
        await update.message.reply_text("Repo was not being tracked.")

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tracked = load_tracked()
    if not tracked:
        await update.message.reply_text("No repos are being tracked.")
        return
    msg = "📋 <b>Tracked Repositories:</b>\n" + "\n".join(f"- <b>{r}</b>" for r in tracked)
    await update.message.reply_text(msg, parse_mode="HTML")

# /releases with inline pagination if too many
async def cmd_releases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tracked = load_tracked()
    if not tracked:
        await update.message.reply_text("No repos are being tracked.")
        return
    page = 0
    await show_releases_page(update, context, tracked, page)

async def show_releases_page(update, context, tracked, page_idx):
    PAGE_SIZE = RELEASES_PAGE_SIZE
    start = page_idx * PAGE_SIZE
    end = start + PAGE_SIZE
    subset = tracked[start:end]
    text_title = f"📦 <b>Latest releases ({start+1}-{min(end, len(tracked))} / {len(tracked)})</b>\n\n"
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_latest_release(session, repo) for repo in subset]
        releases_list = await asyncio.gather(*tasks)
    msg = text_title
    for repo, rel in zip(subset, releases_list):
        if rel:
            tag = rel.get("tag_name", "")
            date = rel.get("published_at", "")[:10]
            name = rel.get("name", "") or ""
            msg += f"🔹 <b>{repo}</b> — <code>{tag}</code> ({date}) {name}\n"
        else:
            msg += f"🔸 <b>{repo}</b>: No release\n"
    nav_buttons = []
    if page_idx > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Back", callback_data=f"rel_page:{page_idx-1}"))
    if end < len(tracked):
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"rel_page:{page_idx+1}"))
    reply_markup = InlineKeyboardMarkup([nav_buttons] if nav_buttons else [])
    if getattr(update, 'message', None):
        await update.message.reply_text(msg, parse_mode="HTML", reply_markup=reply_markup)
    else:  # editing prev page
        await update.callback_query.edit_message_text(msg, parse_mode="HTML", reply_markup=reply_markup)

async def cb_rel_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    m = re.match(r"rel_page:(\d+)", query.data)
    idx = int(m.group(1))
    tracked = load_tracked()
    await show_releases_page(update, context, tracked, idx)

async def cmd_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tracked = load_tracked()
    n = len(tracked)
    if not n:
        await update.message.reply_text("No repos are being tracked.")
        return
    repo_counts = []
    async with aiohttp.ClientSession() as session:
        for repo in tracked:
            url = f'https://api.github.com/repos/{repo}/releases'
            headers = {'Accept': 'application/vnd.github+json'}
            if GITHUB_TOKEN:
                headers['Authorization'] = f'token {GITHUB_TOKEN}'
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    releases = await resp.json()
                    repo_counts.append((repo, len(releases)))
                else:
                    repo_counts.append((repo, 0))
    chart = "\n".join([f"{name}: " + "▇" * min(count,20) + (f" ({count})" if count else "") for name, count in repo_counts])
    await update.message.reply_text(f"📊 <b>Release Count Chart</b>:\n{chart}", parse_mode="HTML")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "<b>This bot tracks GitHub releases and notifies the channel!</b>\n\n"
        "Commands:\n"
        "/add user/repo — Add repo to track\n"
        "/remove user/repo — Stop tracking repo\n"
        "/list — Show all tracked repos\n"
        "/releases — Show latest tracked releases\n"
        "/chart — Release count chart\n"
        "/notify user/repo — Instantly notify channel about latest release\n"
        "/clearall — Remove all tracked repos\n"
        "/ping — Bot health check\n"
        "/help — Show this help\n"
        "/about — About this bot\n\n"
        "<i>You can also send a repo name (user/repo or link) to add it quickly.</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 <b>GitHub Release Notifier Bot</b>\n"
        "Tracks any public repo and pushes beautiful updates with files to your channel.\n"
        "Built for power users and channels.\n"
        "— <i>Powered by python-telegram-bot v20+</i>",
        parse_mode="HTML"
    )

async def cmd_clearall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tracked = load_tracked()
    if not tracked:
        await update.message.reply_text("Nothing to clear!")
        return
    await update.message.reply_text(
        "⚠️ Are you sure you want to remove ALL tracked repos? Type 'YES' to confirm.",
        reply_markup=ReplyKeyboardMarkup([["YES"], ["Cancel"]], resize_keyboard=True)
    )
    context.user_data['awaiting_clearall'] = True

async def handle_clearall_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_clearall'):
        txt = (update.message.text or "").strip().lower()
        if txt == "yes":
            save_tracked([])
            await update.message.reply_text(
                "All tracked repos cleared!", reply_markup=ReplyKeyboardRemove()
            )
        else:
            await update.message.reply_text(
                "Action cancelled.", reply_markup=ReplyKeyboardRemove()
            )
        context.user_data['awaiting_clearall'] = False
        return True
    return False

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is alive and running!")

async def cmd_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Please provide a repo, e.g., /notify user/repo")
        return
    repo = get_repo_name(" ".join(args))
    if not repo:
        await update.message.reply_text("Please provide a valid repo name or link.")
        return
    async with aiohttp.ClientSession() as session:
        release = await fetch_latest_release(session, repo)
    if not release:
        await update.message.reply_text(f"No releases found for {repo}")
        return
    await send_channel_notification(context, release, repo)
    await update.message.reply_text(
        f"Notified channel about latest release for <b>{just_repo(repo)}</b>.",
        parse_mode="HTML"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await handle_clearall_reply(update, context):
        return
    text = update.message.text or ""
    if get_repo_name(text):
        await handle_add(update, context)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("releases", cmd_releases))
    app.add_handler(CommandHandler("chart", cmd_chart))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("about", cmd_about))
    app.add_handler(CommandHandler("clearall", cmd_clearall))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("notify", cmd_notify))
    app.add_handler(MessageHandler(
        filters.TEXT & (~filters.COMMAND), handle_message
    ))
    app.add_handler(CallbackQueryHandler(cb_rel_page, pattern=r"rel_page:\d+"))
    print("Bot running…")
    app.run_polling()

if __name__ == '__main__':
    main()
