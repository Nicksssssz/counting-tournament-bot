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
    749049630775312524: "AA",
    222222222222222222: "BB",
    333333333333333333: "CC",
    444444444444444444: "DD",
}

# -------- LEADERBOARD NICKNAMES (USER ID → DISPLAY NAME) --------
user_nicknames = {
    749049630775312524: "nicks",
}

# -------- STORAGE --------
DATA_DIR = "/data" if os.getenv("RAILWAY_ENVIRONMENT") else "."
DATA_FILE = os.path.join(DATA_DIR, "run_data.json")

# -------- STATE --------
run_active = False

total_counts_by_user = defaultdict(int)
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

    team_counts.update(data.get("team_counts", {}))


def save_data():
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "total_counts_by_user": dict(total_counts_by_user),
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
def get_user_team_by_id(uid: int):
    return user_team_mapping.get(uid)

def get_display_name(uid: int):
    if uid in user_nicknames:
        return user_nicknames[uid]

    user = bot.get_user(uid)
    if user:
        return user.name

    return f"User {uid}"

def is_valid_count_message(content: str) -> bool:
    content = content.lstrip()
    if not content:
        return False

    parts = content.split(" ", 1)
    number_part = parts[0]

    return number_part.isdigit()

# -------- MESSAGE LISTENER --------
@bot.event
async def on_message(message: discord.Message):
    global run_active

    if message.author.bot or message.author.system:
        return
    if not run_active or message.channel.id not in TRACK_CHANNELS:
        return

    if not is_valid_count_message(message.content or ""):
        return

    async with counts_lock:
        uid = message.author.id
        run_counts_by_user[uid] += 1
        total_counts_by_user[uid] += 1

        team = get_user_team_by_id(uid)
        if team:
            team_counts[team] += 1

# -------- RUN TIMER TASK --------
async def run_timer(channel: discord.abc.Messageable):
    global run_active

    await asyncio.sleep(60)

    async with counts_lock:
        run_active = False
        save_data()

        leaderboard_items = sorted(
            run_counts_by_user.items(),
            key=lambda x: -x[1]
        )

    if not leaderboard_items:
        leaderboard_text = "No numbers were counted."
    else:
        lines = []
        for i, (uid, count) in enumerate(leaderboard_items, start=1):
            name = get_display_name(uid)
            lines.append(f"**#{i}** {name}, **{count:,}**")
        leaderboard_text = "\n".join(lines)

    embed = discord.Embed (title="**USERS LEADERBOAD**", description=leaderboard_text, color=0xCCA958)

    await channel.send("Run ended! Totals saved.", embed=embed)

# -------- SLASH COMMANDS --------
@bot.tree.command(name="start_run", description="Starts the 24 hours attempt in both channels.")
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
        "Run started! Stats are now being collected for the next 24 hours."
    )

    bot.loop.create_task(run_timer(interaction.channel))


@bot.tree.command(name="leaderboard_users", description="Shows total numbers counted by each user.")
async def leaderboard_users(interaction: discord.Interaction):
    async with counts_lock:
        leaderboard_items = sorted(
            total_counts_by_user.items(),
            key=lambda x: -x[1]
        )

    if not leaderboard_items:
        await interaction.response.send_message(
            "No data available yet.",
            ephemeral=True
        )
        return

    lines = []
    for i, (uid, count) in enumerate(leaderboard_items, start=1):
        name = get_display_name(uid)
        team = get_user_team_by_id(uid)

        if team:
            lines.append(f"**#{i}** {name} - {team}, **{count:,}**")
        else:
            lines.append(f"**#{i}** {name}, **{count:,}**")

    embed = discord.Embed(
        title="**USERS LEADERBOAD**",
        description="\n".join(lines),
        color=0xCCA958
    )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="show_data", description="Show stored JSON data")
async def show_data(interaction: discord.Interaction):
    if interaction.user.id != 749049630775312524:
        await interaction.response.send_message(
            "You are not allowed to use this command haha bleehhhhh",
            ephemeral=True
        )
        return

    if not os.path.exists(DATA_FILE):
        await interaction.response.send_message(
            "Data file not found... gulp-",
            ephemeral=True
        )
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    text = json.dumps(data, indent=2)

    if len(text) > 1900:
        await interaction.response.send_message(
            "Data is too large to display :p",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"```json\n{text}\n```",
            ephemeral=True
        )

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
