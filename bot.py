import os
import re
import json
import requests
import matplotlib.pyplot as plt
from io import BytesIO
from telegram import Update, ReplyKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ===========================
# Environment PRESET
# ===========================
BOT_TOKEN = os.environ['BOT_TOKEN']
GITHUB_OWNER = os.environ['GITHUB_OWNER']
GITHUB_REPO = os.environ['GITHUB_REPO']
GITHUB_TOKEN = os.environ['GITHUB_TOKEN']
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456"))  # Your Telegram user ID
DATA_PATH = "data/tracked.json"

# ===========================
# GITHUB API I/O
# ===========================

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

# ===========================
# Repo Extraction & Validation
# ===========================

def extract_repos_from_text(text):
    """
    Extract all username/repo or github.com/username/repo links from arbitrary text.
    Allows comma, space, or newline separation.
    """
    pattern = r'(?:https?://github\.com/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)'
    found = re.findall(pattern, text)
    clean = set(f"{u}/{r}" for (u, r) in found)
    return clean

def validate_repo_exists(repo):
    """Return True iff https://github.com/{repo} exists (for add); skip for remove."""
    url = f"https://api.github.com/repos/{repo}"
    r = requests.get(url)
    return r.ok

# ===========================
# HANDLERS
# ===========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["/add", "/remove", "/list", "/releases"],
        ["/chart", "/about", "/help"]
    ]
    await update.message.reply_text(
        "👋 Hi! Paste GitHub repos or use /add, /remove, /list, /chart buttons.\n"
        "Send multiple repos separated by space, comma, or newline.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/add <repo(s)> — Add one or multiple repos (url or username/repo)\n"
        "/remove <repo> — Remove a tracked repo (url or username/repo)\n"
        "/list — Show tracked repos\n"
        "/releases — Show recent releases\n"
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
    text = " ".join(context.args)
    await process_repo_addition(update, text)

async def remove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /remove <repo or link>")
        return
    text = " ".join(context.args)
    repos_to_remove = extract_repos_from_text(text)
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
    msg = ""
    if actually_removed:
        msg += "❌ Removed:\n" + "\n".join(actually_removed)
    if not_found:
        msg += "\nℹ️ Not tracked:\n" + "\n".join(not_found)
    await update.message.reply_text(msg or "Nothing to remove.")

async def any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith('/'):
        return
    text = update.message.text
    await process_repo_addition(update, text)

async def process_repo_addition(update, text):
    repos_to_check = extract_repos_from_text(text)
    if not repos_to_check:
        await update.message.reply_text("No valid repositories found in your message.")
        return
    added, skipped, failed = [], [], []
    repos, sha = load_tracked()
    for repo in repos_to_check:
        if repo in repos:
            skipped.append(repo)
            continue
        if validate_repo_exists(repo):
            repos.append(repo)
            added.append(repo)
        else:
            failed.append(repo)
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
    msg = ""
    for repo in repos:
        resp = requests.get(f"https://api.github.com/repos/{repo}/releases")
        releases = resp.json() if resp.ok else []
        if releases:
            rel = releases[0]
            msg += f"🔹 [{repo}]({rel['html_url']}): [{rel['tag_name']}]({rel['html_url']})\n"
        else:
            msg += f"🔸 {repo}: No releases 👀\n"
    await update.message.reply_text(msg, parse_mode="Markdown", disable_web_page_preview=True)

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
        except Exception: pass
        months = [r["published_at"][:7] for r in releases if "published_at" in r]
        for month in months:
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

# ===========================
# BOT REGISTRATION
# ===========================

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
    app.add_handler(CommandHandler("clearall", clearall_cmd))
    app.add_handler(CommandHandler("chart", chart_cmd))
    # Universal message handler for all non-command text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_message))
    app.run_polling()
