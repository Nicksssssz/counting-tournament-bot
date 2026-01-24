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
    1060539711871004734, #commands
    987737957530239026,  # dms
    1052340912216358993, # juiz
    1343071180327751720  # eba
}

# -------- CONSTANTS --------
MISTAKE_BOT_CHANNEL_ID = 510016054391734273
MISTAKE_BOT_RUINED_ID = 639599059036012605

# -------- TEAMS --------
user_team_mapping = {
    749049630775312524: "eba",
    497517322206969856: "eba",
    709650885487099985: "eba",
    333333333333333333: "CC",
    444444444444444444: "DD"
}

# -------- NICKNAMES --------
user_nicknames = {
    749049630775312524: "nicks",
    497517322206969856: "isa",
    709650885487099985: "gab"
}

# -------- ALTS --------
alt_to_main = {
    # ALT_ID: MAIN_ID,
    866803634964529162: 749049630775312524, #nicks
    984550127400259695: 709650885487099985  #gab
}

# -------- STORAGE --------
DATA_DIR = "/data" if os.getenv("RAILWAY_ENVIRONMENT") else "."
DATA_FILE = os.path.join(DATA_DIR, "run_data.json")

# -------- STATE --------
run_active = False
run_start_time = None
last_valid_user_id = None
current_run_team = None  # <-- team assigned to the current run (set on first valid number)

total_counts_by_user = defaultdict(int)
team_counts = defaultdict(int)
team_mistakes = defaultdict(int)

run_counts_by_user = defaultdict(int)
run_team_mistakes = defaultdict(int)

# store per-team attempt history: team -> list of { "correct": int, "incorrect": int, "accuracy": float or None, "best_1min": int }
team_accuracy_history = defaultdict(list)

# For fastest 1-hour sliding window analysis
RUN_ANALYSIS_WINDOW_HOURS = 24   # total run duration
FASTEST_WINDOW_SECONDS = 3600   # 1 hour window
SAMPLE_INTERVAL_SECONDS = 10    # keep this
run_minute_snapshots = []  # cumulative totals sampled during run (every SAMPLE_INTERVAL_SECONDS seconds)

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

    # load accuracy history (keys are team names)
    for team, runs in data.get("team_accuracy_history", {}).items():
        # runs should be list of dicts; keep as-is
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

def format_accuracy_value(correct: int, incorrect: int):
    total = correct + incorrect
    if total == 0:
        return None
    acc = (correct / total) * 100
    return acc

def format_accuracy_display(acc_value):
    # acc_value is float percent or None
    if acc_value is None:
        return "N/A"
    if acc_value == 100:
        return "100%"
    return f"{acc_value:06.3f}%"

# -------- SECONDARY SAMPLER TASK (every SAMPLE_INTERVAL_SECONDS) --------
async def minute_sampler():
    """
    Samples cumulative run counts once immediately at start, then every SAMPLE_INTERVAL_SECONDS seconds
    up to RUN_ANALYSIS_WINDOW_MINUTES minutes (or until the run ends).
    """
    total_samples = (RUN_ANALYSIS_WINDOW_HOURS * 3600) // SAMPLE_INTERVAL_SECONDS
    # initial snapshot at time 0
    async with counts_lock:
        run_minute_snapshots.append(sum(run_counts_by_user.values()))
    for _ in range(total_samples):
        await asyncio.sleep(SAMPLE_INTERVAL_SECONDS)
        async with counts_lock:
            if not run_active:
                break
            run_minute_snapshots.append(sum(run_counts_by_user.values()))

# -------- MESSAGE LISTENER --------
@bot.event
async def on_message(message: discord.Message):
    global last_valid_user_id, current_run_team

    # ---- Mistake detection (channel / RUINED bots) ----
    if run_active and message.author.id in {MISTAKE_BOT_CHANNEL_ID, MISTAKE_BOT_RUINED_ID}:
        content = (message.content or "").lower()
        if ("of" in content and message.author.id == MISTAKE_BOT_CHANNEL_ID) or (
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
        raw_uid = message.author.id
        uid = resolve_main_user_id(raw_uid)

        last_valid_user_id = uid

        # assign run team on first valid number
        if current_run_team is None:
            current_run_team = get_user_team(uid)

        run_counts_by_user[uid] += 1
        total_counts_by_user[uid] += 1

        team = get_user_team(uid)
        if team:
            team_counts[team] += 1

# -------- RUN TIMER --------
async def run_timer(channel: discord.abc.Messageable):
    global run_active, current_run_team

    await asyncio.sleep(30*60)

    async with counts_lock:
        run_active = False

        leaderboard_items = sorted(
            run_counts_by_user.items(),
            key=lambda x: -x[1]
        )

        mistakes_snapshot = dict(run_team_mistakes)
        correct = sum(run_counts_by_user.values())
        incorrect = sum(mistakes_snapshot.values())
        total_attempts = correct + incorrect

        # compute numeric accuracy value (percent) and store per-team attempt
        acc_value = format_accuracy_value(correct, incorrect)

        # compute best 1-minute (60s) sliding-window delta using run_minute_snapshots
        best_1hour = 0
        window_samples = FASTEST_WINDOW_SECONDS // SAMPLE_INTERVAL_SECONDS
        # need at least window_samples+1 snapshots to compute deltas (start and end)
        if len(run_minute_snapshots) > window_samples:
            deltas = []
            N = len(run_minute_snapshots)
            # for each starting index i where i+window_samples < N
            for i in range(0, N - window_samples):
                delta = run_minute_snapshots[i + window_samples] - run_minute_snapshots[i]
                deltas.append(delta)
            if deltas:
                best_1hour = max(deltas)

        if current_run_team:
            # append attempt record for that team
            team_accuracy_history[current_run_team].append({
                "correct": correct,
                "incorrect": incorrect,
                # store numeric value or None
                "accuracy": acc_value,
                "best_1hour": best_1hour
            })

        # persist data
        save_data()

    # prepare display
    if total_attempts == 0:
        accuracy_text = "N/A"
    else:
        accuracy_text = "100%" if acc_value == 100 else (format_accuracy_display(acc_value) if acc_value is not None else "N/A")

    if not leaderboard_items:
        leaderboard_text = "No numbers were counted."
    else:
        lines = []
        for i, (uid, count) in enumerate(leaderboard_items, start=1):
            name = get_display_name(uid)
            lines.append(f"**#{i}** {name}, **{count:,}**")
        leaderboard_text = "\n".join(lines)

    embed = discord.Embed(
        title=f"**FINAL RUN STATS: {current_run_team.upper() if current_run_team else 'NO TEAM'}**",
        description=(
            f"Correct Rate: **{accuracy_text}**\n"
            f"✅ **{correct:,}**\n"
            f"❌ **{incorrect:,}**\n\n"
            f"{leaderboard_text}\n\n"
            f"**Best 1-hour period:** **{best_1hour:,}**"
        ),
        color=0xCCA958
    )

    message = await channel.send(embed=embed)

    await message.pin()

    # clear run-only state
    run_counts_by_user.clear()
    run_team_mistakes.clear()
    run_minute_snapshots.clear()
    current_run_team = None

# -------- SLASH COMMANDS --------
@bot.tree.command(name="start_run", description="Starts a run or shows current run status.")
async def start_run(interaction: discord.Interaction):
    global run_active, run_start_time, last_valid_user_id, current_run_team

    async with counts_lock:
        if run_active:
            elapsed = int(time.time() - run_start_time)

            correct = sum(run_counts_by_user.values())
            incorrect = sum(run_team_mistakes.values())
            total_attempts = correct + incorrect

            if total_attempts == 0:
                accuracy_text = "N/A"
            else:
                acc_val = format_accuracy_value(correct, incorrect)
                accuracy_text = "100%" if acc_val == 100 else (format_accuracy_display(acc_val) if acc_val is not None else "N/A")

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

            embed = discord.Embed(
                title="**CURRENT RUN STATUS**",
                description=(
                    f"Time: **{format_duration(elapsed)}**\n"
                    f"Correct Rate: **{accuracy_text}**\n"
                    f"✅ **{correct:,}**\n"
                    f"❌ **{incorrect:,}**\n\n"
                    f"{leaderboard}"
                ),
                color=0xCCA958
            )

            await interaction.response.send_message(embed=embed)
            return

        run_active = True
        run_start_time = time.time()
        last_valid_user_id = None
        current_run_team = None
        run_counts_by_user.clear()
        run_team_mistakes.clear()
        run_minute_snapshots.clear()

    await interaction.response.send_message(
        "24 hours attempt started! Stats are now being collected."
    )

    # start run timer and minute sampler
    bot.loop.create_task(run_timer(interaction.channel))
    bot.loop.create_task(minute_sampler())

@bot.tree.command(name="leaderboard_users", description="Shows total numbers counted by each user and which team they belong to.")
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

@bot.tree.command(name="leaderboard_accuracy", description="Shows accuracy leaderboard for all team attempts.")
async def leaderboard_accuracy(interaction: discord.Interaction):
    # collect (team, attempt_index, accuracy_value)
    entries = []
    async with counts_lock:
        for team, runs in team_accuracy_history.items():
            for idx, run in enumerate(runs, start=1):
                acc = run.get("accuracy")
                if acc is None:
                    continue
                # acc is numeric percent
                entries.append((team, idx, float(acc)))

    if not entries:
        await interaction.response.send_message("No accuracy data available yet.")
        return

    # sort descending by accuracy
    entries.sort(key=lambda x: -x[2])

    lines = []
    for rank, (team, attempt, value) in enumerate(entries, start=1):
        if value == 100:
            acc_text = "100%"
        else:
            acc_text = f"{value:06.3f}%"
        lines.append(f"**#{rank}** {team} ({attempt}) - **{acc_text}**")

    embed = discord.Embed(
        title="**ACCURACY LEADERBOARD**",
        description="\n".join(lines),
        color=0xCCA958
    )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="leaderboard_numbers", description="Shows numbers counted per team attempt.")
async def leaderboard_numbers(interaction: discord.Interaction):
    # collect (team, attempt_index, correct_count)
    entries = []
    async with counts_lock:
        for team, runs in team_accuracy_history.items():
            for idx, run in enumerate(runs, start=1):
                count = int(run.get("correct", 0))
                entries.append((team, idx, count))

    if not entries:
        await interaction.response.send_message("No run data available yet.")
        return

    # sort descending by count
    entries.sort(key=lambda x: -x[2])

    lines = []
    for rank, (team, attempt, count) in enumerate(entries, start=1):
        lines.append(f"**#{rank}** {team} ({attempt}) - **{count:,}**")

    embed = discord.Embed(
        title="**NUMBERS LEADERBOARD**",
        description="\n".join(lines),
        color=0xCCA958
    )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="show_data", description="Shows raw stored data).")
async def show_data(interaction: discord.Interaction):
    if interaction.user.id != 749049630775312524:
        await interaction.response.send_message(
            "You are not allowed to use this command silly :p",
            ephemeral=True
        )
        return

    async with counts_lock:
        data_snapshot = {
            "total_counts_by_user": dict(total_counts_by_user),
            "team_counts": dict(team_counts),
            "team_mistakes": dict(team_mistakes),
            "team_accuracy_history": dict(team_accuracy_history),
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
    print(f"Logged in as {bot.user} (ID: {bot.user.id}")
    print(f"Data file: {DATA_FILE}")

# -------- RUN --------
bot.run(TOKEN, log_handler=handler)
