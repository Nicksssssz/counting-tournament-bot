import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import asyncio
import json
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

# -------- TEAMS --------
user_team_mapping = {
    111111111111111111: "CS",
    222222222222222222: "CS",
}

# -------- STORAGE --------
DATA_DIR = "/data" if os.getenv("RAILWAY_ENVIRONMENT") else "."
DATA_FILE = os.path.join(DATA_DIR, "run_data.json")

# -------- STATE --------
run_active = False

total_counts_by_user = defaultdict(int)
user_usernames = {}
team_counts = defaultdict(int)

run_counts_by_user = defaultdict(int)
counts_lock = asyncio.Lock()

# -------- LOAD / SAVE --------
def load_data():
    if not os.path.exists(DATA_FILE):
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    for uid, count in data.get("total_counts_by_user", {}).items():
        total_counts_by_user[int(uid)] = count

    user_usernames.update({int(k): v for k, v in data.get("user_usernames", {}).items()})
    team_counts.update(data.get("team_counts", {}))


def save_data():
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "total_counts_by_user": dict(total_counts_by_user),
            "user_usernames": user_usernames,
            "team_counts": dict(team_counts)
        }, f, indent=2)

# -------- AUTOSAVE --------
async def autosave_loop():
    while True:
        await asyncio.sleep(10)
        async with counts_lock:
            if run_active:
                save_data()

# -------- HELPERS --------
def get_user_team(member: discord.Member):
    return user_team_mapping.get(member.id)

# -------- MESSAGE LISTENER --------
@bot.event
async def on_message(message: discord.Message):
    global run_active

    if message.author.bot or message.author.system:
        return
    if not run_active or message.channel.id not in TRACK_CHANNELS:
        return

    content = (message.content or "").lstrip()
    if not content or not content[0].isdigit():
        return

    async with counts_lock:
        uid = message.author.id
        run_counts_by_user[uid] += 1
        total_counts_by_user[uid] += 1
        user_usernames[uid] = message.author.name

        team = get_user_team(message.author)
        if team:
            team_counts[team] += 1

# -------- SLASH COMMAND --------
@bot.tree.command(name="start_run", description="Starts a counting run.")
async def start_run(interaction: discord.Interaction):
    global run_active

    if run_active:
        await interaction.response.send_message("A run is already active.", ephemeral=True)
        return

    async with counts_lock:
        run_active = True
        run_counts_by_user.clear()

    await interaction.response.send_message("Run started! Stats are now being collected.")

    # ⏱️ RUN DURATION
    await asyncio.sleep(3600*8)

    async with counts_lock:
        run_active = False
        save_data()

        leaderboard_items = sorted(
            total_counts_by_user.items(),
            key=lambda x: -x[1]
        )

    if not leaderboard_items:
        leaderboard_text = "No numbers were counted."
    else:
        lines = []
        for i, (uid, count) in enumerate(leaderboard_items, start=1):
            name = user_usernames.get(uid, f"User {uid}")
            lines.append(f"**#{i}** {name}, **{count:,}**")
        leaderboard_text = "\n".join(lines)

    embed = discord.Embed(
        title="**GLOBAL LEADERBOARD**",
        description=leaderboard_text
    )

    await interaction.followup.send("Run ended! Totals saved.", embed=embed)

# -------- READY --------
@bot.event
async def on_ready():
    load_data()
    bot.loop.create_task(autosave_loop())
    await bot.tree.sync()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Data file: {DATA_FILE}")

# -------- RUN --------
bot.run(TOKEN, log_handler=handler)
