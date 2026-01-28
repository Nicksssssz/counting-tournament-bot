import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import asyncio
import json
import time
from collections import defaultdict, deque

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
    1315525836341907560, #classic col
    1315492435115114517, # contando col
    1052340912216358993  # juiz
}

COMMANDS_CHANNEL_ID = 1060539711871004734

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
    984550127400259695: 709650885487099985, #gab
    892551131488743434: 497517322206969856  #isa
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

run_counts_by_user = defaultdict(int)
run_team_mistakes = defaultdict(int)

# store per-team attempt history: team -> list of { "correct": int, "incorrect": int, "accuracy": float or None, "best_1hour": int, "best_1hour_start": int, "top_users": [str,...] }
team_accuracy_history = defaultdict(list)

# For fastest 1-hour sliding window analysis
RUN_ANALYSIS_WINDOW_HOURS = 24   # total run duration (used for number of samples)
FASTEST_WINDOW_SECONDS = 3600   # 1 hour window
SAMPLE_INTERVAL_SECONDS = 10    # keep this (sampling resolution)
# per-channel snapshots (cumulative totals sampled during run every SAMPLE_INTERVAL_SECONDS)
run_snapshots_per_channel = defaultdict(list)

# per-channel running counters during run (all users)
run_counts_by_channel = defaultdict(int)

# per-channel per-user cumulative counters during run
run_user_counts_by_channel = defaultdict(lambda: defaultdict(int))
# per-channel per-user sampled snapshots lists
run_user_snapshots_per_channel = defaultdict(lambda: defaultdict(list))

# last 40 senders per channel (to detect 2-person start) <- changed from 50 to 40
last_50_senders_per_channel = defaultdict(lambda: deque(maxlen=40))

# two-person run state per channel
# structure: ch_id -> { 'active': bool, 'runners': (uid1, uid2), 'start_time': float }
two_person_runs = {}

# history of two-person runs during the attempt, per channel
# structure: ch_id -> [ { "runners": (uid1, uid2), "start": ts, "end": ts, "duration": secs } , ... ]
run_two_person_history_per_channel = defaultdict(list)

counts_lock = asyncio.Lock()

# -------- LOAD / SAVE --------
def load_data():
    if not os.path.exists(DATA_FILE):
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    for uid, count in data.get("total_counts_by_user", {}).items():
        total_counts_by_user[int(uid)] = count

    # load accuracy history (keys are team names)
    for team, runs in data.get("team_accuracy_history", {}).items():
        team_accuracy_history[team] = runs


def save_data():
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "total_counts_by_user": dict(total_counts_by_user),
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
    up to RUN_ANALYSIS_WINDOW_HOURS hours (or until the run ends).
    Stores per-channel cumulative snapshots into run_snapshots_per_channel and per-user snapshots into run_user_snapshots_per_channel.
    Also checks active two-person runs every sample (to enforce 100 numbers in last 10 minutes rule).
    """
    total_samples = (RUN_ANALYSIS_WINDOW_HOURS * 3600) // SAMPLE_INTERVAL_SECONDS
    # initial snapshot at time 0 for each tracked channel
    async with counts_lock:
        for ch in TRACK_CHANNELS:
            run_snapshots_per_channel[ch].append(run_counts_by_channel.get(ch, 0))
            # per-user: initialize existing users snapshot
            users = set(run_user_counts_by_channel[ch].keys()) | set(run_user_snapshots_per_channel[ch].keys())
            for u in users:
                # initial value
                val = run_user_counts_by_channel[ch].get(u, 0)
                run_user_snapshots_per_channel[ch][u].append(val)
    for _ in range(total_samples):
        await asyncio.sleep(SAMPLE_INTERVAL_SECONDS)
        async with counts_lock:
            if not run_active:
                break
            for ch in TRACK_CHANNELS:
                run_snapshots_per_channel[ch].append(run_counts_by_channel.get(ch, 0))
                # per-user snapshots: ensure every tracked user has a value appended to keep lists aligned
                users = set(run_user_counts_by_channel[ch].keys()) | set(run_user_snapshots_per_channel[ch].keys())
                for u in users:
                    val = run_user_counts_by_channel[ch].get(u, None)
                    if val is None:
                        # preserve last known value if user not present in current counts
                        prev_list = run_user_snapshots_per_channel[ch].get(u, [])
                        val = prev_list[-1] if prev_list else 0
                    run_user_snapshots_per_channel[ch][u].append(val)

            # After sampling, check two-person runs for activity condition (100 numbers in last 10 minutes)
            samples_in_10min = (10 * 60) // SAMPLE_INTERVAL_SECONDS
            to_end = []
            now_ts = time.time()
            for ch, state in list(two_person_runs.items()):
                if not state.get("active"):
                    continue
                runners = state["runners"]
                run_start_time = state.get("start_time", now_ts)
                # if this run hasn't reached 10 minutes since its own start, skip the check
                if now_ts - run_start_time < 10 * 60:
                    continue
                # need snapshots for both users
                snaps = run_user_snapshots_per_channel.get(ch, {})
                u1, u2 = runners
                list1 = snaps.get(u1, [])
                list2 = snaps.get(u2, [])
                # ensure we have enough samples to look back samples_in_10min
                if len(list1) <= samples_in_10min or len(list2) <= samples_in_10min:
                    # not enough historical samples yet -> keep running until we have enough
                    continue
                curr1 = list1[-1]
                prev1 = list1[-1 - samples_in_10min]
                curr2 = list2[-1]
                prev2 = list2[-1 - samples_in_10min]
                delta1 = curr1 - prev1
                delta2 = curr2 - prev2
                delta = delta1 + delta2
                # End run if combined < 100 OR if any runner contributed 0 in last 10 minutes
                if delta < 100 or delta1 < 1 or delta2 < 1:
                    to_end.append(ch)
            # end runs that failed the check
            for ch in to_end:
                state = two_person_runs.get(ch)
                if not state:
                    continue
                runners = state["runners"]
                start_time = state["start_time"]
                end_time = time.time()
                duration = int(end_time - start_time)
                duration_text = format_duration(duration)
                # append to history
                run_two_person_history_per_channel[ch].append({
                    "runners": runners,
                    "start": start_time,
                    "end": end_time,
                    "duration": duration
                })
                # announce in commands channel (send clickable channel mention)
                cmd_ch = bot.get_channel(COMMANDS_CHANNEL_ID)
                runners_display = " & ".join(get_display_name(u) for u in runners)
                ch_mention = f"<#{ch}>"
                if cmd_ch:
                    await cmd_ch.send(f"Run ended in {ch_mention}!\nRunners: {runners_display}\nTotal time was: **{duration_text}**")
                # remove state
                del two_person_runs[ch]

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

        # increment per-channel running counter
        run_counts_by_channel[message.channel.id] += 1

        # increment per-channel per-user counter
        run_user_counts_by_channel[message.channel.id][uid] += 1

        # append sender to last-40 deque for that channel (for detection)
        dq = last_50_senders_per_channel[message.channel.id]
        dq.append(uid)

        # detection: if deque full (len==40) and plugin not already active, check unique senders
        if len(dq) == dq.maxlen:
            unique = set(dq)
            if len(unique) == 2:
                runners = tuple(sorted(unique))
                # if there's no active two-person run for this channel, start one
                state = two_person_runs.get(message.channel.id)
                if not state or not state.get("active"):
                    # start the two-person run
                    two_person_runs[message.channel.id] = {
                        "active": True,
                        "runners": runners,
                        "start_time": time.time()
                    }
                    # announce in commands channel (clickable mention)
                    cmd_ch = bot.get_channel(COMMANDS_CHANNEL_ID)
                    runners_display = " & ".join(get_display_name(u) for u in runners)
                    ch_mention = f"<#{message.channel.id}>"
                    if cmd_ch:
                        await cmd_ch.send(f"A new run has started in {ch_mention}\nRunners: {runners_display}")

# -------- RUN TIMER --------
async def run_timer(channel: discord.abc.Messageable):
    global run_active, current_run_team

    await asyncio.sleep(60*60+60*10)

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

        # compute best 1-hour sliding-window delta per channel using run_snapshots_per_channel
        best_1hour = 0
        best_channel = None
        best_start_index = 0
        window_samples = FASTEST_WINDOW_SECONDS // SAMPLE_INTERVAL_SECONDS
        # iterate channels and compute deltas
        for ch, snapshots in run_snapshots_per_channel.items():
            N = len(snapshots)
            if N <= window_samples:
                continue
            # scan all possible windows
            for i in range(0, N - window_samples):
                delta = snapshots[i + window_samples] - snapshots[i]
                if delta > best_1hour:
                    best_1hour = delta
                    best_channel = ch
                    best_start_index = i

        # compute start seconds relative to run (multiple of SAMPLE_INTERVAL_SECONDS)
        best_start_seconds = best_start_index * SAMPLE_INTERVAL_SECONDS if best_channel is not None else 0

        # determine top users for this run (up to 2) for storage
        top_users_for_run = []
        if leaderboard_items:
            for uid, cnt in leaderboard_items:
                team = get_user_team(uid)
                if team == current_run_team:
                    top_users_for_run.append(get_display_name(uid))
                if len(top_users_for_run) >= 2:
                    break

        # finalize any still-active two-person runs as ending now and append to history
        now_ts = time.time()
        for ch, state in list(two_person_runs.items()):
            if state.get("active"):
                runners = state["runners"]
                start_time = state["start_time"]
                end_time = now_ts
                duration = int(end_time - start_time)
                run_two_person_history_per_channel[ch].append({
                    "runners": runners,
                    "start": start_time,
                    "end": end_time,
                    "duration": duration
                })
        # (do NOT delete two_person_runs here — we will clear after embed creation to preserve other logic)

        if current_run_team:
            # append attempt record for that team
            team_accuracy_history[current_run_team].append({
                "correct": correct,
                "incorrect": incorrect,
                # store numeric value or None
                "accuracy": acc_value,
                "best_1hour": best_1hour,
                "best_1hour_start": best_start_seconds,
                "top_users": top_users_for_run
            })

        # persist data
        save_data()

        # compute longest two-person run across channels for this attempt
        longest_duration = 0
        longest_runners = None
        longest_channel = None
        for ch, runs in run_two_person_history_per_channel.items():
            for rec in runs:
                if rec["duration"] > longest_duration:
                    longest_duration = rec["duration"]
                    longest_runners = rec["runners"]
                    longest_channel = ch

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

    # get channel mention (clickable) if possible
    if best_channel is not None:
        best_channel_mention = f"<#{best_channel}>"
        best_start_text = format_duration(best_start_seconds)
    else:
        best_channel_mention = "N/A"
        best_start_text = "00:00:00"

    # longest run display
    if longest_duration > 0 and longest_runners:
        longest_duration_text = format_duration(longest_duration)
        longest_participants = " & ".join(f"**{get_display_name(u)}**" for u in longest_runners)
        longest_block = f"Longest run: **{longest_duration_text}**\nParticipants: {longest_participants}\n\n"
    else:
        longest_block = ""

    # compute attempt number for the team (attempt #)
    attempt_number = len(team_accuracy_history[current_run_team]) if current_run_team in team_accuracy_history else 1

    embed = discord.Embed(
        title=f"**{current_run_team.upper() if current_run_team else 'NO TEAM'}'S ATTEMPT #{attempt_number} STATS:**",
        description=(
            f"Fastest 1-hour run: **{best_1hour:,}**\n"
            f"Started at: **{best_start_text}**\n\n"
            f"{longest_block}"
            f"Correct Rate: **{accuracy_text}**\n"
            f"✅ **{correct:,}**\n"
            f"❌ **{incorrect:,}**\n\n"
            f"{leaderboard_text}"
        ),
        color=0xCCA958
    )

    message = await channel.send(embed=embed)

    await message.pin()

    # clear run-only state
    run_counts_by_user.clear()
    run_team_mistakes.clear()
    run_snapshots_per_channel.clear()
    run_user_snapshots_per_channel.clear()
    run_counts_by_channel.clear()
    run_user_counts_by_channel.clear()
    last_50_senders_per_channel.clear()
    two_person_runs.clear()
    run_two_person_history_per_channel.clear()
    current_run_team = None

# -------- SLASH COMMANDS --------
@bot.tree.command(name="run", description="Starts a run or shows current run status.")
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
        run_snapshots_per_channel.clear()
        run_counts_by_channel.clear()
        run_user_counts_by_channel.clear()
        run_user_snapshots_per_channel.clear()
        last_50_senders_per_channel.clear()
        two_person_runs.clear()
        run_two_person_history_per_channel.clear()

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

@bot.tree.command(name="leaderboard_fastest", description="Shows fastest 1-hour runs with top users and team.")
async def leaderboard_fastest(interaction: discord.Interaction):
    # collect (team, attempt_index, best_1hour, top_users)
    entries = []
    async with counts_lock:
        for team, runs in team_accuracy_history.items():
            for idx, run in enumerate(runs, start=1):
                best = int(run.get("best_1hour", 0))
                if best <= 0:
                    continue
                top_users = run.get("top_users", []) or []
                entries.append((team, idx, best, top_users))

    if not entries:
        await interaction.response.send_message("No fastest-run data available yet.")
        return

    # sort descending by best value
    entries.sort(key=lambda x: -x[2])

    lines = []
    for rank, (team, attempt, best, top_users) in enumerate(entries, start=1):
        if top_users:
            # join up to 2 users with " & "
            display_users = " & ".join(top_users[:2])
            lines.append(f"**#{rank}** {display_users} - {team}, **{best:,}**")
        else:
            lines.append(f"**#{rank}** {team}, **{best:,}**")

    embed = discord.Embed(
        title="**FASTEST RUN LEADERBOARD**",
        description="\n".join(lines),
        color=0xCCA958
    )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="show_data", description="Shows raw stored data.")
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
