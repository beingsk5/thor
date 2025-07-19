import os
import json
import re
import requests
import matplotlib.pyplot as plt
from io import BytesIO
from telegram import Update, ReplyKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TELEGRAM_BOT_TOKEN = os.environ['BOT_TOKEN']
GITHUB_OWNER = os.environ['GITHUB_OWNER']      # e.g. beingsk5
GITHUB_REPO = os.environ['GITHUB_REPO']        # e.g. tracker-data
GITHUB_TOKEN = os.environ['GITHUB_TOKEN']      # PAT (repo contents)
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456"))

DATA_PATH = "data/tracked.json"


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
        "message": "Update tracked repos via bot",
        "content": b64encode(new_data.encode()).decode(),
        "sha": sha
    }
    r = requests.put(url, headers=github_headers(), json=payload)
    r.raise_for_status()
    return r.json()['content']['sha']


def parse_repo(text):
    m = re.match(r"^(?:https?://github\.com/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:.git)?/?$", text.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["/add", "/list", "/releases"],
        ["/chart", "/about", "/help"]
    ]
    await update.message.reply_text(
        "👋 Hi! Use the menu buttons or commands.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/add <repo> — Add new repo (url or username/repo)\n"
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
        "• Persistent data in your GitHub repo\n"
        "• Fully automatic via GitHub Actions\n"
        "• Channel notifications & README badge"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Bot is alive!")


async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /add <repo_url or username/repo>")
        return
    repo = parse_repo(context.args[0])
    if not repo:
        await update.message.reply_text("❗ Invalid format. Try username/repo or GitHub link.")
        return
    repos, sha = load_tracked()
    if repo in repos:
        await update.message.reply_text("Already tracking that repo.")
        return
    repos.append(repo)
    save_tracked(repos, sha)
    await update.message.reply_text(f"✅ Now tracking `{repo}`", parse_mode='Markdown')

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
        months = [r["published_at"][:7] for r in releases]  # yyyy-mm
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

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("releases", releases_cmd))
    app.add_handler(CommandHandler("clearall", clearall_cmd))
    app.add_handler(CommandHandler("chart", chart_cmd))
    app.run_polling()
