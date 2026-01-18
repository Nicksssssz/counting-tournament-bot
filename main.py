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
MISTAKE_BOT_ID = 510016054391734273

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

# -------- STORAGE --------
DATA_DIR = "/data" if os.getenv("RAILWAY_ENVIRONMENT") else "."
DATA_FILE = os.path.join(DATA_DIR, "run_data.json")

# -------- STATE --------
run_active = False
run_start_time = None
last_valid_user_id = None

total_counts_by_user = defaultdict(int)
team_counts = defaultdict(int)
team_mistakes = defaultdict(int)

run_counts_by_user = defaultdict(int)
run_team_mistakes = defaultdict(int)

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


def save_data():
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "total_counts_by_user": dict(total_counts_by_user),
            "team_counts": dict(team_counts),
            "team_mistakes": dict(team_mistakes),
        }, f, indent=2)

# -------- AUTOSAVE --------
async def autosave_loop():
    while True:
        await asyncio.sleep(10)
        async with counts_lock:
            if run_active:
                save_data()

# -------- HELPERS --------
def get_user_team(uid: int):
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
    return content.split(" ", 1)[0].isdigit()

def format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"

# -------- MESSAGE LISTENER --------
@bot.event
async def on_message(message: discord.Message):
    global last_valid_user_id

    # ---- Mistake detection ----
    if (
        run_active
        and message.author.id == MISTAKE_BOT_ID
        and "channel" in (message.content or "").lower()
    ):
        async with counts_lock:
            if last_valid_user_id is not None:
                run_counts_by_user[last_valid_user_id] = max(
                    0, run_counts_by_user[last_valid_user_id] - 1
                )
                total_counts_by_user[last_valid_user_id] = max(
                    0, total_counts_by_user[last_valid_user_id] - 1
                )

                team = get_user_team(last_valid_user_id)
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
        uid = message.author.id
        last_valid_user_id = uid

        run_counts_by_user[uid] += 1
        total_counts_by_user[uid] += 1

        team = get_user_team(uid)
        if team:
            team_counts[team] += 1

# -------- RUN TIMER --------
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

        mistakes_snapshot = dict(run_team_mistakes)
        correct = sum(run_counts_by_user.values())
        incorrect = sum(mistakes_snapshot.values())
        total_attempts = correct + incorrect

    if total_attempts == 0:
        accuracy_text = "N/A"
    else:
        accuracy = (correct / total_attempts) * 100
        accuracy_text = "100%" if accuracy == 100 else f"{accuracy:06.3f}%"

    if not leaderboard_items:
        leaderboard_text = "No numbers were counted."
    else:
        lines = []
        for i, (uid, count) in enumerate(leaderboard_items, start=1):
            name = get_display_name(uid)
            lines.append(f"**#{i}** {name}, **{count:,}**")
        leaderboard_text = "\n".join(lines)

    embed = discord.Embed(
        title="**FINAL RUN STATS**",
        description=(
            f"**Accuracy:** {accuracy_text}\n"
            f"✅ **{correct:,}**\n"
            f"❌ **{incorrect:,}**\n\n"
            f"{leaderboard_text}"
        ),
        color=0xCCA958
    )

    await channel.send(embed=embed)


# -------- SLASH COMMANDS --------
@bot.tree.command(name="start_run", description="Starts a run or shows current run status.")
async def start_run(interaction: discord.Interaction):
    global run_active, run_start_time, last_valid_user_id

    async with counts_lock:
        if run_active:
            elapsed = int(time.time() - run_start_time)

            correct = sum(run_counts_by_user.values())
            incorrect = sum(run_team_mistakes.values())
            total_attempts = correct + incorrect

            if total_attempts == 0:
                accuracy_text = "N/A"
            else:
                accuracy = (correct / total_attempts) * 100
                accuracy_text = "100%" if accuracy == 100 else f"{accuracy:06.3f}%"

            items = sorted(
                run_counts_by_user.items(),
                key=lambda x: -x[1]
            )

            leaderboard = (
                "\n".join(
                    f"**#{i}** {get_display_name(uid)}, **{count:,}**"
                    for i, (uid, count) in enumerate(items, start=1)
                )
                if items else
                "No numbers counted yet."
            )

            mistakes_text = (
                f"{incorrect:,}"
                if incorrect > 0 else
                "0"
            )

            embed = discord.Embed(
                title="**CURRENT RUN STATUS**",
                description=(
                    f"**Time:** {format_duration(elapsed)}\n\n"
                    f"**{accuracy_text}**\n"
                    f"✅ **{correct:,}**\n"
                    f"❌ **{mistakes_text}**\n\n"
                    f"{leaderboard}"
                ),
                color=0xCCA958
            )

            await interaction.response.send_message(embed=embed)
            return


        run_active = True
        run_start_time = time.time()
        last_valid_user_id = None
        run_counts_by_user.clear()
        run_team_mistakes.clear()

    await interaction.response.send_message(
        "Run started! Stats are now being collected."
    )

    bot.loop.create_task(run_timer(interaction.channel))


@bot.tree.command(name="leaderboard_users", description="Shows total numbers counted by each user.")
async def leaderboard_users(interaction: discord.Interaction):
    async with counts_lock:
        items = sorted(
            total_counts_by_user.items(),
            key=lambda x: -x[1]
        )

    if not items:
        await interaction.response.send_message(
            "No data available yet.",
            ephemeral=True
        )
        return

    lines = []
    for i, (uid, count) in enumerate(items, start=1):
        name = get_display_name(uid)
        team = get_user_team(uid)
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


@bot.tree.command(name="show_data", description="Shows raw stored data (admin only).")
async def show_data(interaction: discord.Interaction):
    if interaction.user.id != 749049630775312524:
        await interaction.response.send_message(
            "You are not allowed to use this command.",
            ephemeral=True
        )
        return

    async with counts_lock:
        data_snapshot = {
            "total_counts_by_user": dict(total_counts_by_user),
            "team_counts": dict(team_counts),
            "team_mistakes": dict(team_mistakes),
        }

    pretty = json.dumps(data_snapshot, indent=2)

    await interaction.response.send_message(
        f"```json\n{pretty}\n```",
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
