import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import asyncio
import json
import time
from collections import defaultdict

# -------- ENV --------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# -------- LOGGING --------
handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")

# -------- INTENTS --------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# -------- BOT --------
bot = commands.Bot(command_prefix=None, intents=intents)

# -------- CHANNELS --------
TRACK_CHANNELS = {
    1060539711871004734,
    987737957530239026
}

# -------- CONSTANTS --------
MISTAKE_BOT_CHANNEL_ID = 510016054391734273
MISTAKE_BOT_RUINED_ID = 639599059036012605

# -------- TEAMS --------
user_team_mapping = {
    749049630775312524: "AA",
    222222222222222222: "BB",
    333333333333333333: "CC",
    444444444444444444: "DD",
}

# -------- NICKNAMES --------
user_nicknames = {
    749049630775312524: "nicks",
}

# -------- ALTS --------
alt_to_main = {
    866803634964529162: 749049630775312524,
}

# -------- STORAGE --------
DATA_DIR = "/data" if os.getenv("RAILWAY_ENVIRONMENT") else "."
DATA_FILE = os.path.join(DATA_DIR, "run_data.json")

# -------- STATE --------
run_active = False
run_start_time = None
last_valid_user_id = None
current_run_team = None

total_counts_by_user = defaultdict(int)
team_counts = defaultdict(int)
team_mistakes = defaultdict(int)

run_counts_by_user = defaultdict(int)
run_team_mistakes = defaultdict(int)

# team -> list of accuracy values (one per attempt)
team_accuracy_history = defaultdict(list)

counts_lock = asyncio.Lock()

# -------- LOAD / SAVE --------
def load_data():
    if not os.path.exists(DATA_FILE):
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    for uid, count in data.get("total_counts_by_user", {}).items():
        total_counts_by_user[int(uid)] = count

    team_counts.update(data.get("team_counts", {}))
    team_mistakes.update(data.get("team_mistakes", {}))

    for team, runs in data.get("team_accuracy_history", {}).items():
        team_accuracy_history[team] = runs


def save_data():
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "total_counts_by_user": dict(total_counts_by_user),
            "team_counts": dict(team_counts),
            "team_mistakes": dict(team_mistakes),
            "team_accuracy_history": dict(team_accuracy_history),
        }, f, indent=2)

# -------- AUTOSAVE --------
async def autosave_loop():
    while True:
        await asyncio.sleep(10)
        async with counts_lock:
            if run_active:
                save_data()

# -------- HELPERS --------
def resolve_main_user_id(uid: int) -> int:
    return alt_to_main.get(uid, uid)

def get_user_team(uid: int):
    return user_team_mapping.get(uid)

def get_display_name(uid: int):
    if uid in user_nicknames:
        return user_nicknames[uid]
    user = bot.get_user(uid)
    return user.name if user else f"User {uid}"

def is_valid_count_message(content: str) -> bool:
    content = content.lstrip()
    if not content:
        return False
    first = content.split(" ", 1)[0]
    return first.isdigit()

def format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"

def format_accuracy(correct: int, incorrect: int) -> str:
    total = correct + incorrect
    if total == 0:
        return "N/A"
    acc = (correct / total) * 100
    return "100%" if acc == 100 else f"{acc:06.3f}%"

# -------- MESSAGE LISTENER --------
@bot.event
async def on_message(message: discord.Message):
    global last_valid_user_id, current_run_team

    # ---- Mistake detection ----
    if run_active and message.author.id in {MISTAKE_BOT_CHANNEL_ID, MISTAKE_BOT_RUINED_ID}:
        content = (message.content or "").lower()
        if ("channel" in content and message.author.id == MISTAKE_BOT_CHANNEL_ID) or (
            "ruined" in content and message.author.id == MISTAKE_BOT_RUINED_ID
        ):
            async with counts_lock:
                if last_valid_user_id is not None:
                    uid = last_valid_user_id
                    run_counts_by_user[uid] = max(0, run_counts_by_user[uid] - 1)
                    total_counts_by_user[uid] = max(0, total_counts_by_user[uid] - 1)

                    team = get_user_team(uid)
                    if team:
                        team_mistakes[team] += 1
                        run_team_mistakes[team] += 1
            return

    # ---- Normal counting ----
    if message.author.bot or message.author.system:
        return
    if not run_active or message.channel.id not in TRACK_CHANNELS:
        return
    if not is_valid_count_message(message.content or ""):
        return

    async with counts_lock:
        uid = resolve_main_user_id(message.author.id)
        last_valid_user_id = uid

        # Assign run team on first valid number
        if current_run_team is None:
            current_run_team = get_user_team(uid)

        run_counts_by_user[uid] += 1
        total_counts_by_user[uid] += 1

        team = get_user_team(uid)
        if team:
            team_counts[team] += 1

# -------- RUN TIMER --------
async def run_timer(channel):
    global run_active, current_run_team

    await asyncio.sleep(60)

    async with counts_lock:
        run_active = False

        correct = sum(run_counts_by_user.values())
        incorrect = sum(run_team_mistakes.values())
        accuracy = format_accuracy(correct, incorrect)

        if current_run_team:
            team_accuracy_history[current_run_team].append({
                "correct": correct,
                "incorrect": incorrect,
                "accuracy": accuracy
            })

        save_data()

        leaderboard = sorted(run_counts_by_user.items(), key=lambda x: -x[1])

    lines = [
        f"**#{i}** {get_display_name(uid)}, **{count:,}**"
        for i, (uid, count) in enumerate(leaderboard, start=1)
    ] or ["No numbers were counted."]

    embed = discord.Embed(
        title="**FINAL RUN STATS**",
        description=(
            f"Correct Rate: **{accuracy}**\n"
            f"✅ **{correct:,}**\n"
            f"❌ **{incorrect:,}**\n\n" +
            "\n".join(lines)
        ),
        color=0xCCA958
    )

    await channel.send(embed=embed)

    run_counts_by_user.clear()
    run_team_mistakes.clear()
    current_run_team = None

# -------- SLASH COMMANDS --------
@bot.tree.command(name="leaderboard_accuracy", description="Shows accuracy leaderboard by team attempts.")
async def leaderboard_accuracy(interaction: discord.Interaction):
    entries = []

    for team, runs in team_accuracy_history.items():
        for i, run in enumerate(runs, start=1):
            acc = run["accuracy"]
            if acc != "N/A":
                entries.append((team, i, float(acc.strip("%"))))

    if not entries:
        await interaction.response.send_message("No accuracy data available yet.")
        return

    entries.sort(key=lambda x: -x[2])

    lines = [
        f"**#{i}** {team} ({attempt}) - **{value:06.3f}%**"
        for i, (team, attempt, value) in enumerate(entries, start=1)
    ]

    embed = discord.Embed(
        title="**ACCURACY LEADERBOARD**",
        description="\n".join(lines),
        color=0xCCA958
    )

    await interaction.response.send_message(embed=embed)

# -------- READY --------
@bot.event
async def on_ready():
    load_data()
    bot.loop.create_task(autosave_loop())
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")
    print(f"Data file: {DATA_FILE}")

# -------- RUN --------
bot.run(TOKEN, log_handler=handler)
