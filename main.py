import os
import json
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackContext, filters
from datetime import datetime

REPO_FILE = "repos.json"
HISTORY_FILE = "history.json"
DEFAULT_REPOS = os.getenv("TRACKED_REPOS", "")

def load_json(path, fallback):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(fallback, f, indent=2)
    with open(path) as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def load_repos():
    return load_json(REPO_FILE, DEFAULT_REPOS.split() if DEFAULT_REPOS else [])

def load_history():
    return load_json(HISTORY_FILE, {})

def save_all(repos, history):
    save_json(REPO_FILE, repos)
    save_json(HISTORY_FILE, history)

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("👋 Welcome to GitHub Release Tracker Bot!")

async def help_command(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "📖 *Available Commands:*\n"
        "/start - Welcome message\n"
        "/help - Show this help\n"
        "/about - About the bot\n"
        "/list - Show tracked repositories\n"
        "/clearall - Remove all tracked repositories\n"
        "/ping - Check if bot is alive\n"
        "/releases - Show recent releases\n"
        "/chart - Show chart of tracked repos",
        parse_mode="Markdown"
    )

async def about_command(update: Update, context: CallbackContext):
    await update.message.reply_text("🤖 GitHub Release Tracker Bot by @beingsk\nOpen-source and customizable.")

async def ping_command(update: Update, context: CallbackContext):
    await update.message.reply_text("🏓 Pong! Bot is active.")

async def clearall_command(update: Update, context: CallbackContext):
    save_all([], {})
    await update.message.reply_text("🧹 All tracked repositories cleared.")

async def list_command(update: Update, context: CallbackContext):
    repos = load_repos()
    if not repos:
        await update.message.reply_text("📭 No repositories are being tracked.")
    else:
        reply = "📦 *Currently Tracked Repositories:*\n" + "\n".join(f"🔹 `{r}`" for r in repos)
        await update.message.reply_text(reply, parse_mode="Markdown")

async def releases_command(update: Update, context: CallbackContext):
    history = load_history()
    if not history:
        await update.message.reply_text("📭 No releases found in history.")
        return
    reply = "🕘 *Latest Releases:*\n"
    for repo, data in history.items():
        reply += f"🔹 `{repo}` - [{data['tag']}]({data['url']})\n"
    await update.message.reply_text(reply, parse_mode="Markdown", disable_web_page_preview=True)

async def chart_command(update: Update, context: CallbackContext):
    chart_url = "https://raw.githubusercontent.com/beingsk5/thor/main/badges/tracked_count_badge.svg"
    await update.message.reply_photo(photo=chart_url, caption="📊 Current Tracked Repository Count")

async def handle_message(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    repos = load_repos()
    added = []

    # Extract GitHub repos
    repo_names = re.findall(r"(?:https?://github\.com/)?([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)", text)
    for repo in repo_names:
        if repo not in repos:
            repos.append(repo)
            added.append(repo)

    save_all(repos, load_history())

    if added:
        await update.message.reply_text(
            f"✅ Added {len(added)} new repo(s) to tracking.\n📦 Total: {len(repos)}"
        )
    else:
        await update.message.reply_text("ℹ️ No new repositories were added.")

def main():
    token = os.getenv("TELEGRAM_TOKEN")
    app = Application.builder().token(token).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("ping", ping_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("clearall", clearall_command))
    app.add_handler(CommandHandler("releases", releases_command))
    app.add_handler(CommandHandler("chart", chart_command))

    # Fallback handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == "__main__":
    main()
