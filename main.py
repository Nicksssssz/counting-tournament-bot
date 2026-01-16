import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import asyncio
import json
from collections import defaultdict

# -----------------------
# ENV / TOKEN
# -----------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# -----------------------
# LOGGING
# -----------------------
handler = logging.FileHandler(
    filename="discord.log",
    encoding="utf-8",
    mode="w"
)

# -----------------------
# INTENTS
# -----------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# -----------------------
# BOT
# -----------------------
bot = commands.Bot(
    command_prefix=None,
    intents=intents
)

# -----------------------
# CHANNELS TO TRACK
# -----------------------
TRACK_CHANNELS = {
    1060539711871004734,
    987737957530239026
}

# -----------------------
# TEAM MAPPING
# -----------------------
user_team_mapping = {
    # user_id: "TEAM"
    111111111111111111: "CS",
    222222222222222222: "CS",
}

# -----------------------
# STORAGE PATH (Railway Volume)
# -----------------------
DATA_DIR = "/data" if os.getenv("RAILWAY_ENVIRONMENT") else "."
DATA_FILE = os.path.join(DATA_DIR, "run_data.json")

# -----------------------
# GLOBAL STATE
# -----------------------
run_active = False

# Persistent (saved)
total_counts_by_user = defaultdict(int)   # user_id -> total count
user_display_names = {}                   # user_id -> display name
team_counts = defaultdict(int)            # team -> total count

# Run-only (resets every run)
run_counts_by_user = defaultdict(int)

counts_lock = asyncio.Lock()

# -----------------------
# LOAD / SAVE FUNCTIONS
# -----------------------
def load_data():
    if not os.path.exists(DATA_FILE):
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    for uid, count in data.get("total_counts_by_user", {}).items():
        total_counts_by_user[int(uid)] = count

    user_display_names.update(data.get("user_display_names", {}))
    team_counts.update(data.get("team_counts", {}))


def save_data():
    data = {
        "total_counts_by_user": dict(total_counts_by_user),
        "user_display_names": user_display_names,
        "team_counts": dict(team_counts),
    }

    os.makedirs(DATA_DIR, exist_ok=True)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# -----------------------
# HELPER
# -----------------------
def get_user_team(member: discord.Member):
    return user_team_mapping.get(member.id)

# -----------------------
# MESSAGE LISTENER
# -----------------------
@bot.event
async def on_message(message: discord.Message):
    global run_active

    if message.author.bot or message.author.system:
        return

    if not run_active:
        return

    if message.channel.id not in TRACK_CHANNELS:
        return

    content = (message.content or "").lstrip()
    if not content or not content[0].isdigit():
        return

    async with counts_lock:
        uid = message.author.id

        # Run-only
        run_counts_by_user[uid] += 1

        # Persistent totals
        total_counts_by_user[uid] += 1
        user_display_names[uid] = message.author.display_name

        team = get_user_team(message.author)
        if team:
            team_counts[team] += 1

# -----------------------
# SLASH COMMAND
# -----------------------
@bot.tree.command(
    name="start_run",
    description="Starts a counting run."
)
async def start_run(interaction: discord.Interaction):
    global run_active

    if run_active:
        await interaction.response.send_message(
            "A run is already active.",
            ephemeral=True
        )
        return

    async with counts_lock:
        run_active = True
        run_counts_by_user.clear()

    await interaction.response.send_message(
        "Run started! Stats are now being collected."
    )

    # ⏱ CHANGE THIS TO 24 * 60 * 60 LATER
    await asyncio.sleep(60*30)

    async with counts_lock:
        run_active = False
        save_data()

        leaderboard_items = sorted(
            total_counts_by_user.items(),
            key=lambda x: -x[1]
        )

    # Build leaderboard
    if not leaderboard_items:
        leaderboard_text = "No numbers were counted."
    else:
        lines = []
        for i, (uid, count) in enumerate(leaderboard_items, start=1):
            name = user_display_names.get(uid, f"User {uid}")
            lines.append(f"#{i} {name}, {count}")
        leaderboard_text = "\n".join(lines)

    embed = discord.Embed(
        title="**GLOBAL LEADERBOARD**",
        description=leaderboard_text
    )

    await interaction.followup.send(
        "Run ended! Totals have been saved.",
        embed=embed
    )

# -----------------------
# READY
# -----------------------
@bot.event
async def on_ready():
    load_data()
    await bot.tree.sync()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Data file: {DATA_FILE}")

# -----------------------
# RUN
# -----------------------
bot.run(TOKEN, log_handler=handler)
