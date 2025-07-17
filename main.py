# main.py
import os
import json
import logging
import requests
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

REPO_FILE = "repos.json"
HISTORY_FILE = "history.json"

BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", "0"))  # Set your Telegram ID in .env

logging.basicConfig(level=logging.INFO)

def load_json(filename, fallback):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    return fallback

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

def validate_repo_format(repo: str) -> bool:
    parts = repo.strip().split("/")
    return len(parts) == 2 and all(parts)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hello! Send me a GitHub repo link or use /help")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧭 *GitHub Release Bot Commands:*\n"
        "/add <repo_url or user/repo> - Track a new repo\n"
        "/list - Show tracked repos\n"
        "/releases - Show recent releases\n"
        "/chart - Repo activity chart\n"
        "/ping - Check bot status\n"
        "/about - Info about this bot\n"
        "/clearall - Clear all (admin only)",
        parse_mode="Markdown"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong!")

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 GitHub Release Tracker Bot by beingsk\n🔗 https://github.com/beingsk5/thor")

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_json(REPO_FILE, {"repos": []})
    if not data["repos"]:
        await update.message.reply_text("❌ No repositories are being tracked.")
    else:
        msg = "📦 *Tracked Repositories:*\n" + "\n".join(f"- `{r['name']}`" for r in data["repos"])
        await update.message.reply_text(msg, parse_mode="Markdown")

async def clearall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != BOT_OWNER_ID:
        await update.message.reply_text("🚫 Only the bot owner can clear all.")
        return
    save_json(REPO_FILE, {"repos": []})
    save_json(HISTORY_FILE, {})
    await update.message.reply_text("✅ All tracked repositories cleared.")

async def add_repo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text.strip()
    repos = [r.strip() for r in msg.split() if "/" in r]

    if not repos:
        await update.message.reply_text("⚠️ Please provide valid GitHub repos (username/repo)")
        return

    current = load_json(REPO_FILE, {"repos": []})
    existing = set(r["name"] for r in current["repos"])
    added = 0

    for repo in repos:
        repo = repo.replace("https://github.com/", "").strip()
        if validate_repo_format(repo) and repo not in existing:
            current["repos"].append({"name": repo})
            added += 1

    save_json(REPO_FILE, current)
    await update.message.reply_text(f"✅ Added {added} new repositories.\n📦 Total: {len(current['repos'])}")

def main():
    token = os.getenv("BOT_TOKEN")
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("clearall", clearall))
    app.add_handler(CommandHandler("add", add_repo))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), add_repo))

    app.run_polling()

if __name__ == "__main__":
    main()
