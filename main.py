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
    1315525836341907560, # classic col
    1315492435115114517  # contando col
}

COMMANDS_CHANNEL_ID = 1060539711871004734

# -------- CONSTANTS --------
MISTAKE_BOT_CHANNEL_ID = 510016054391734273
MISTAKE_BOT_RUINED_ID = 639599059036012605

# two-person run thresholds
TWO_PERSON_DETECTION_WINDOW = 40     # how many recent messages to inspect to detect a 2-person pair
TWO_PERSON_MIN_COUNT = 95            # changed from 100 -> 95 (numbers in last 10 minutes required)
TWO_PERSON_WARNING_MINUTES = 9       # send warning if last 9 minutes < TWO_PERSON_MIN_COUNT
TWO_PERSON_CHECK_MINUTES = 10        # check inactivity over last 10 minutes

# -------- TEAMS --------
teams = {
    "eba": [749049630775312524, 497517322206969856, 709650885487099985, 665011985121017894, 992014751381065791,
            1327841688147984558, 762417923574726667, 1189250809020555344, 91628137384808448, 1136159374511968438,
            1267712959589912598, 875155347541721100, 593889062377488435, 855351859039174677, 1200505072493285544,
            1290390298958233720, 848670503182794763, 514078286146699265, 1275494343293272166, 177013970895503360,
            903692413300793434, 747859758354137128, 713936728481857637, 1063269856251740180, 1156662987357171854,
            586031901207166976, 890989360701386754, 770794762780409856, 249881368945885184, 1137835454671097906,
            832596613922684968, 1146434565179723899, 495708539462090762, 885123109630406706, 904224456677945364,
            547612876530122763, 1403694438143889498, 1221444926819270763, 895534695729725500, 577666133549645834,
            735957682913017866, 668223790500544512, 485412155596996628, 154721499159199744, 572231874525659189,
            456613134682030081, 953238846852702238, 392459609283100672, 130452258864234496, 817022469004984340,
            784701362536448001, 484484139349835781, 815837012648919050, 520341628049686538, 886617454867013642,
            655855955304644629, 309840548695638026, 1198658950082609299, 1178268672373030975, 1274417682975952948
    ],
    "dxrk": [1,
    ],
    "hope": [2,
    ],
    "ⅩⅩⅡ": [3,
    ],
    "Chicago Stix": [4,
    ]
}

user_team_mapping = {
    user_id: team
    for team, users in teams.items()
    for user_id in users
}


# -------- NICKNAMES --------
user_nicknames = {
    749049630775312524:  "nicks",
    497517322206969856:  "isa",
    709650885487099985:  "gab",
    665011985121017894:  "nicoel",
    992014751381065791:  "khyma",
    1327841688147984558: "thiran",
    762417923574726667:  "logan",
    1189250809020555344: "dark",
    91628137384808448:   "A*",
    1136159374511968438: "ama",
    1267712959589912598: "arya",
    875155347541721100:  "axo",
    593889062377488435:  "azure",
    855351859039174677:  "bertl",
    1200505072493285544: "claret",
    1290390298958233720: "cobrakai",
    848670503182794763:  "deepblue",
    514078286146699265:  "digi",
    1275494343293272166: "dodge",
    177013970895503360:  "duck",
    903692413300793434:  "hope",
    747859758354137128:  "iron",
    713936728481857637:  "jake",
    1063269856251740180: "james",
    1156662987357171854: "jdubs",
    586031901207166976:  "kailee",
    890989360701386754:  "korl",
    770794762780409856:  "leaw",
    249881368945885184:  "leti",
    1137835454671097906: "lost",
    832596613922684968:  "maddie",
    1146434565179723899: "lite",
    495708539462090762:  "marcin",
    885123109630406706:  "milk",
    904224456677945364:  "nai",
    547612876530122763:  "nap",
    1403694438143889498: "nssleo",
    1221444926819270763: "sonic",
    895534695729725500:  "stick",
    577666133549645834:  "onyan",
    735957682913017866:  "onyx",
    668223790500544512:  "pia",
    485412155596996628:  "quv",
    154721499159199744:  "raydop",
    572231874525659189:  "rreae",
    456613134682030081:  "sall",
    953238846852702238:  "salt",
    392459609283100672:  "saud",
    130452258864234496:  "scan",
    817022469004984340:  "schpark",
    784701362536448001: "shelley",
    484484139349835781: "skilo",
    815837012648919050: "super",
    520341628049686538: "trashcore",
    886617454867013642: "zgames",
    655855955304644629: "kazuma",
    309840548695638026: "w0rd",
    1198658950082609299:"storydreamer",
    1178268672373030975:"willy",
    1274417682975952948:"bruce"
}

# -------- ALTS --------
alt_to_main = {
    # ALT_ID: MAIN_ID,
    866803634964529162: 749049630775312524,  # nicks
    984550127400259695: 709650885487099985,  # gab
    892551131488743434: 497517322206969856,  # isa
    1260746158553305222: 497517322206969856, # isa2
    1207827979451768862: 665011985121017894, # nicoel
    
    1176872999287279710: 992014751381065791, # "khyma"
    1347500051441909760: 1327841688147984558,# "thiran"
    1: 762417923574726667, # "logan"
    1189255952797536339: 1189250809020555344,# "dark"
    0: 91628137384808448,  # "A*"
    305414646972809216: 1136159374511968438, # "ama"
    1414033725045473281: 1267712959589912598,# "arya"
    1079617884633968720: 875155347541721100, # "axo"
    1248216922760151075: 593889062377488435, # "azure"
    1222912258594705519: 855351859039174677, # "bertl"
    0: 1200505072493285544,# "claret"
    1293661110066483323: 1290390298958233720,# "cobrakai"
    1153637098751004722: 848670503182794763, # "deepblue"
    1: 514078286146699265, # "digi"
    1370859001469993052: 1275494343293272166,# "dodge"
    0: 177013970895503360, # "duck"
    1214592526510456872: 903692413300793434, # "hope"
    1082448603789922386: 747859758354137128, # "iron"
    955603875421904966: 713936728481857637,  # "jake"
    0: 1063269856251740180,# "james"
    1348389360122466347: 1156662987357171854,# "jdubs"
    419233067312611329: 586031901207166976,  # "kailee"
    936197474115276810: 890989360701386754,  # "korl"
    1329622073978388532: 770794762780409856, # "leaw"
    1298027245478350942: 249881368945885184, # "leti"
    1201311902085685338: 1137835454671097906,# "lost"
    0: 832596613922684968, # "maddie"
    0: 1146434565179723899,# "lite"
    898089548905578506: 495708539462090762,  # "marcin"
    915622952257601596: 885123109630406706,  # "milk"
    1247146814281613408: 904224456677945364, # "nai"
    0: 547612876530122763, # "nap"
    0: 1403694438143889498,# "nssleo"
    1: 1221444926819270763,# "sonic"
    452322112707756032: 895534695729725500,  # "stick"
    627998970320388106: 577666133549645834,  # "onyan"
    1305061438959779871: 735957682913017866, # "onyx"
    0: 668223790500544512, # "pia"
    592670631854735361: 485412155596996628,  # "quv"
    1345019952310259732: 154721499159199744, # "raydop"
    0: 572231874525659189, # "rreae"
    0: 456613134682030081, # "sall"
    1223120985109041194: 953238846852702238, # "salt"
    1239981964153327734: 392459609283100672, # "saud"
    0: 130452258864234496, # "scan"
    1420868900295413790: 817022469004984340, # "schpark"
    0: 784701362536448001, # "shelley"
    1374386220259610746: 484484139349835781, # "skilo"
    1: 815837012648919050, # "super"
    964996735908843520: 520341628049686538,  # "trashcore"
    1146121542560927905: 886617454867013642, # "zgames"
    0: 655855955304644629, # "kazuma"
    0: 309840548695638026, # "w0rd"
    0: 1198658950082609299,# "storydreamer"
    1065819724082065489: 1178268672373030975,# "willy"
    1348101708974391357: 1274417682975952948 # "bruce"
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

# store per-team attempt history: team -> list of { "correct": int, "incorrect": int, "accuracy": float or None, "best_1hour": int, "best_1hour_start": int, "top_users": [str,...], "two_person_runs": [...] }
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

# last N senders per channel (to detect 2-person start)
last_50_senders_per_channel = defaultdict(lambda: deque(maxlen=TWO_PERSON_DETECTION_WINDOW))

# two-person run state per channel
# structure: ch_id -> { 'active': bool, 'runners': (uid1, uid2), 'start_time': float, 'warned': bool }
two_person_runs = {}

# history of two-person runs during the attempt, per channel
# structure: ch_id -> [ { "runners": (uid1, uid2), "start": ts, "end": ts, "duration": secs } , ... ]
run_two_person_history_per_channel = defaultdict(list)

# background task references (so /end_run can cancel them)
run_timer_task = None
run_sampler_task = None

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
    # valid if begins with digits and next char (if any) is whitespace or end-of-string
    first_token = content.split(" ", 1)[0]
    return first_token.isdigit()

def format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"

def format_duration_hours_minutes(seconds: int) -> str:
    # For leaderboard_longest display as HH:MM (no seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h:02}:{m:02}"

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

# -------- UTIL: finalize two-person run --------
def _append_two_person_history(ch: int, runners: tuple, start_ts: float, end_ts: float):
    duration = int(end_ts - start_ts)
    run_two_person_history_per_channel[ch].append({
        "runners": runners,
        "start": start_ts,
        "end": end_ts,
        "duration": duration
    })

async def finalize_two_person_run(ch: int, *, end_ts: float = None, clear_deque: bool = True, announce_in_commands: bool = True):
    """
    Finalize an active two-person run in channel ch.
    - end_ts: optional explicit end timestamp (defaults to now)
    - clear_deque: if True, clear the last-N deque to avoid immediate restart
    - announce_in_commands: if True, post a 'Run ended' message to the commands channel
    """
    if end_ts is None:
        end_ts = time.time()
    state = two_person_runs.get(ch)
    if not state:
        return
    runners = state["runners"]
    start_ts = state.get("start_time", end_ts)
    _append_two_person_history(ch, runners, start_ts, end_ts)

    if announce_in_commands:
        duration = int(end_ts - start_ts)
        duration_text = format_duration(duration)
        cmd_ch = bot.get_channel(COMMANDS_CHANNEL_ID)
        runners_display = " & ".join(get_display_name(u) for u in runners)
        ch_mention = f"<#{ch}>"
        if cmd_ch:
            await cmd_ch.send(f"Run ended in {ch_mention}!\nRunners: {runners_display}\nTotal time was: **{duration_text}**")

    # remove active run state
    if ch in two_person_runs:
        del two_person_runs[ch]

    # clear deque if requested
    if clear_deque:
        last_50_senders_per_channel[ch].clear()

# -------- SECONDARY SAMPLER TASK (every SAMPLE_INTERVAL_SECONDS) --------
async def minute_sampler():
    """
    Samples cumulative run counts once immediately at start, then every SAMPLE_INTERVAL_SECONDS seconds
    up to RUN_ANALYSIS_WINDOW_HOURS hours (or until the run ends).
    Stores per-channel cumulative snapshots into run_snapshots_per_channel and per-user snapshots into run_user_snapshots_per_channel.
    Also checks active two-person runs every sample (to enforce TWO_PERSON_MIN_COUNT numbers in last TWO_PERSON_CHECK_MINUTES).
    Sends a 9-minute warning when appropriate.
    """
    total_samples = (RUN_ANALYSIS_WINDOW_HOURS * 3600) // SAMPLE_INTERVAL_SECONDS
    # initial snapshot at time 0 for each tracked channel
    async with counts_lock:
        for ch in TRACK_CHANNELS:
            run_snapshots_per_channel[ch].append(run_counts_by_channel.get(ch, 0))
            # per-user: initialize existing users snapshot
            users = set(run_user_counts_by_channel[ch].keys()) | set(run_user_snapshots_per_channel[ch].keys())
            for u in users:
                val = run_user_counts_by_channel[ch].get(u, 0)
                run_user_snapshots_per_channel[ch][u].append(val)

    samples_in_10min = (TWO_PERSON_CHECK_MINUTES * 60) // SAMPLE_INTERVAL_SECONDS
    samples_in_9min = (TWO_PERSON_WARNING_MINUTES * 60) // SAMPLE_INTERVAL_SECONDS

    for _ in range(total_samples):
        await asyncio.sleep(SAMPLE_INTERVAL_SECONDS)
        async with counts_lock:
            if not run_active:
                break

            for ch in TRACK_CHANNELS:
                run_snapshots_per_channel[ch].append(run_counts_by_channel.get(ch, 0))
                users = set(run_user_counts_by_channel[ch].keys()) | set(run_user_snapshots_per_channel[ch].keys())
                for u in users:
                    val = run_user_counts_by_channel[ch].get(u, None)
                    if val is None:
                        prev_list = run_user_snapshots_per_channel[ch].get(u, [])
                        val = prev_list[-1] if prev_list else 0
                    run_user_snapshots_per_channel[ch][u].append(val)

            # After sampling, check two-person runs for activity condition (TWO_PERSON_MIN_COUNT in last 10 minutes)
            to_end = []
            now_ts = time.time()
            for ch, state in list(two_person_runs.items()):
                if not state.get("active"):
                    continue
                runners = state["runners"]
                run_start_time = state.get("start_time", now_ts)

                # WARNING: check the 9-minute warning if run has been active long enough and not yet warned
                if (now_ts - run_start_time) >= (TWO_PERSON_WARNING_MINUTES * 60) and not state.get("warned", False):
                    snaps = run_user_snapshots_per_channel.get(ch, {})
                    u1, u2 = runners
                    list1 = snaps.get(u1, [])
                    list2 = snaps.get(u2, [])
                    if len(list1) > samples_in_9min and len(list2) > samples_in_9min:
                        curr1 = list1[-1]
                        prev1 = list1[-1 - samples_in_9min]
                        curr2 = list2[-1]
                        prev2 = list2[-1 - samples_in_9min]
                        delta9 = (curr1 - prev1) + (curr2 - prev2)
                        if delta9 < TWO_PERSON_MIN_COUNT:
                            # send a single warning in commands channel mentioning the active channel
                            cmd_ch = bot.get_channel(COMMANDS_CHANNEL_ID)
                            ch_mention = f"<#{ch}>"
                            if cmd_ch:
                                await cmd_ch.send(f"The current run in {ch_mention} is close to ending for inactivity!")
                            state['warned'] = True  # mark warned so we don't spam

                # Only check full inactivity rule if run has existed at least TWO_PERSON_CHECK_MINUTES
                if now_ts - run_start_time < (TWO_PERSON_CHECK_MINUTES * 60):
                    continue

                snaps = run_user_snapshots_per_channel.get(ch, {})
                u1, u2 = runners
                list1 = snaps.get(u1, [])
                list2 = snaps.get(u2, [])
                if len(list1) <= samples_in_10min or len(list2) <= samples_in_10min:
                    # still not enough samples -> wait
                    continue

                curr1 = list1[-1]
                prev1 = list1[-1 - samples_in_10min]
                curr2 = list2[-1]
                prev2 = list2[-1 - samples_in_10min]
                delta1 = curr1 - prev1
                delta2 = curr2 - prev2
                delta = delta1 + delta2

                # End run if combined < TWO_PERSON_MIN_COUNT OR if any runner contributed 0 in last 10 minutes
                if delta < TWO_PERSON_MIN_COUNT or delta1 < 1 or delta2 < 1:
                    to_end.append(ch)

            # End the runs that failed the check (inactivity). Announce in commands channel and clear deque.
            for ch in to_end:
                # finalize and clear_deque=True so we don't immediately restart accidentally
                await finalize_two_person_run(ch, clear_deque=True, announce_in_commands=True)

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

        # append sender to last-N deque for that channel (for detection)
        dq = last_50_senders_per_channel[message.channel.id]
        dq.append(uid)

        # detection: if deque full and plugin not already active, check unique senders
        if len(dq) == dq.maxlen:
            unique = set(dq)
            if len(unique) == 2:
                runners = tuple(sorted(unique))
                state = two_person_runs.get(message.channel.id)
                if not state or not state.get("active"):
                    # no active run -> start it
                    two_person_runs[message.channel.id] = {
                        "active": True,
                        "runners": runners,
                        "start_time": time.time(),
                        "warned": False
                    }
                    # announce in commands channel (clickable mention)
                    cmd_ch = bot.get_channel(COMMANDS_CHANNEL_ID)
                    runners_display = " & ".join(get_display_name(u) for u in runners)
                    ch_mention = f"<#{message.channel.id}>"
                    if cmd_ch:
                        await cmd_ch.send(f"A new run has started in {ch_mention}\nRunners: {runners_display}")
                else:
                    # there is an active run in this channel
                    current_runners = state.get("runners")
                    if current_runners != runners:
                        # NEW pair detected — finalize old run and START new run immediately
                        # finalize previous run but do NOT clear deque (so new run detection continues)
                        await finalize_two_person_run(message.channel.id, clear_deque=False, announce_in_commands=True)
                        # start the new run
                        two_person_runs[message.channel.id] = {
                            "active": True,
                            "runners": runners,
                            "start_time": time.time(),
                            "warned": False
                        }
                        cmd_ch = bot.get_channel(COMMANDS_CHANNEL_ID)
                        runners_display = " & ".join(get_display_name(u) for u in runners)
                        ch_mention = f"<#{message.channel.id}>"
                        if cmd_ch:
                            await cmd_ch.send(f"A new run has started in {ch_mention}\nRunners: {runners_display}")

# -------- RUN TIMER (finalize attempt) --------
async def run_timer(channel: discord.abc.Messageable):
    global run_active, current_run_team, run_timer_task

    # original sleep duration preserved (kept same as you had)
    await asyncio.sleep(60*60*60*24)

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
        for ch, snapshots in run_snapshots_per_channel.items():
            N = len(snapshots)
            if N <= window_samples:
                continue
            for i in range(0, N - window_samples):
                delta = snapshots[i + window_samples] - snapshots[i]
                if delta > best_1hour:
                    best_1hour = delta
                    best_channel = ch
                    best_start_index = i

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

        # finalize any still-active two-person runs as ending now and append to history (clear deque)
        now_ts = time.time()
        for ch, state in list(two_person_runs.items()):
            if state.get("active"):
                await finalize_two_person_run(ch, end_ts=now_ts, clear_deque=True, announce_in_commands=False)

        # prepare two_person_runs flattened summary for storing in attempt record
        two_runs_flat = []
        for ch, runs in run_two_person_history_per_channel.items():
            for rec in runs:
                two_runs_flat.append({
                    "channel": ch,
                    "runners": rec["runners"],
                    "start": rec["start"],
                    "end": rec["end"],
                    "duration": rec["duration"]
                })

        if current_run_team:
            team_accuracy_history[current_run_team].append({
                "correct": correct,
                "incorrect": incorrect,
                "accuracy": acc_value,
                "best_1hour": best_1hour,
                "best_1hour_start": best_start_seconds,
                "top_users": top_users_for_run,
                "two_person_runs": two_runs_flat
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

        # determine participants for the best 1-hour window
        best_participants_display = ""
        if best_channel is not None and best_1hour > 0:
            snaps = run_user_snapshots_per_channel.get(best_channel, {})
            start_idx = best_start_index
            end_idx = best_start_index + window_samples
            deltas = []
            for uid, lst in snaps.items():
                if len(lst) > end_idx:
                    delta = lst[end_idx] - lst[start_idx]
                else:
                    try:
                        end_val = lst[end_idx] if end_idx < len(lst) else lst[-1]
                        start_val = lst[start_idx] if start_idx < len(lst) else lst[0]
                        delta = end_val - start_val
                    except Exception:
                        delta = 0
                deltas.append((delta, uid))
            deltas.sort(key=lambda x: -x[0])
            top_uids = [uid for d, uid in deltas if d > 0][:2]
            if top_uids:
                best_participants_display = " & ".join(f"**{get_display_name(u)}**" for u in top_uids)
            else:
                best_participants_display = "N/A"
        else:
            best_participants_display = "N/A"

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

    # get best channel mention if possible
    if best_channel is not None:
        best_channel_mention = f"<#{best_channel}>"
    else:
        best_channel_mention = "N/A"

    # longest run display
    if longest_duration > 0 and longest_runners:
        longest_duration_text = format_duration(longest_duration)
        longest_participants = " & ".join(f"**{get_display_name(u)}**" for u in longest_runners)
        longest_block = f"Longest run: **{longest_duration_text}**\nParticipants: {longest_participants}\n\n"
    else:
        longest_block = ""

    attempt_number = len(team_accuracy_history[current_run_team]) if current_run_team in team_accuracy_history else 1

    embed = discord.Embed(
        title=f"**{current_run_team.upper() if current_run_team else 'NO TEAM'}'S ATTEMPT #{attempt_number} STATS:**",
        description=(
            f"Fastest 1-hour run: **{best_1hour:,}**\n"
            f"Participants: {best_participants_display}\n\n"
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

    run_timer_task = None

# -------- SLASH COMMANDS --------
@bot.tree.command(name="run", description="Starts a run or shows current run status.")
async def start_run(interaction: discord.Interaction):
    global run_active, run_start_time, last_valid_user_id, current_run_team, run_timer_task, run_sampler_task

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

    # start run timer and minute sampler and keep references so /end_run can cancel them
    run_timer_task = bot.loop.create_task(run_timer(interaction.channel))
    run_sampler_task = bot.loop.create_task(minute_sampler())

@bot.tree.command(name="end_run", description="Ends current run immediately. Choose to save the data or not.")
async def end_run(interaction: discord.Interaction, save: bool = True):
    """
    Ends the current run early.
    Option 'save' boolean decides whether to save the attempt into team history and persist to disk.
    """
    global run_active, run_timer_task, run_sampler_task, current_run_team

    async with counts_lock:
        if not run_active:
            await interaction.response.send_message("No active run to end.", ephemeral=True)
            return

        # cancel background tasks if present
        if run_timer_task is not None and not run_timer_task.done():
            run_timer_task.cancel()
        if run_sampler_task is not None and not run_sampler_task.done():
            run_sampler_task.cancel()

        # Immediately perform the same finalization logic from run_timer
        run_active = False

        leaderboard_items = sorted(
            run_counts_by_user.items(),
            key=lambda x: -x[1]
        )

        mistakes_snapshot = dict(run_team_mistakes)
        correct = sum(run_counts_by_user.values())
        incorrect = sum(mistakes_snapshot.values())
        total_attempts = correct + incorrect

        # compute numeric accuracy value (percent)
        acc_value = format_accuracy_value(correct, incorrect)

        # compute best 1-hour sliding-window delta per channel using run_snapshots_per_channel
        best_1hour = 0
        best_channel = None
        best_start_index = 0
        window_samples = FASTEST_WINDOW_SECONDS // SAMPLE_INTERVAL_SECONDS
        for ch, snapshots in run_snapshots_per_channel.items():
            N = len(snapshots)
            if N <= window_samples:
                continue
            for i in range(0, N - window_samples):
                delta = snapshots[i + window_samples] - snapshots[i]
                if delta > best_1hour:
                    best_1hour = delta
                    best_channel = ch
                    best_start_index = i

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
                # use finalize helper -> clear_deque=True (because this is an official end)
                await finalize_two_person_run(ch, end_ts=now_ts, clear_deque=True, announce_in_commands=True)

        # prepare two_person_runs flattened summary for storing in attempt record
        two_runs_flat = []
        for ch, runs in run_two_person_history_per_channel.items():
            for rec in runs:
                two_runs_flat.append({
                    "channel": ch,
                    "runners": rec["runners"],
                    "start": rec["start"],
                    "end": rec["end"],
                    "duration": rec["duration"]
                })

        if current_run_team and save:
            team_accuracy_history[current_run_team].append({
                "correct": correct,
                "incorrect": incorrect,
                "accuracy": acc_value,
                "best_1hour": best_1hour,
                "best_1hour_start": best_start_seconds,
                "top_users": top_users_for_run,
                "two_person_runs": two_runs_flat
            })

        if save:
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

        # determine participants for the best 1-hour window
        best_participants_display = ""
        if best_channel is not None and best_1hour > 0:
            snaps = run_user_snapshots_per_channel.get(best_channel, {})
            start_idx = best_start_index
            end_idx = best_start_index + window_samples
            deltas = []
            for uid, lst in snaps.items():
                if len(lst) > end_idx:
                    delta = lst[end_idx] - lst[start_idx]
                else:
                    try:
                        end_val = lst[end_idx] if end_idx < len(lst) else lst[-1]
                        start_val = lst[start_idx] if start_idx < len(lst) else lst[0]
                        delta = end_val - start_val
                    except Exception:
                        delta = 0
                deltas.append((delta, uid))
            deltas.sort(key=lambda x: -x[0])
            top_uids = [uid for d, uid in deltas if d > 0][:2]
            if top_uids:
                best_participants_display = " & ".join(f"**{get_display_name(u)}**" for u in top_uids)
            else:
                best_participants_display = "N/A"
        else:
            best_participants_display = "N/A"

    # prepare display (outside counts_lock)
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

    if best_channel is not None:
        best_channel_mention = f"<#{best_channel}>"
    else:
        best_channel_mention = "N/A"

    if longest_duration > 0 and longest_runners:
        longest_duration_text = format_duration(longest_duration)
        longest_participants = " & ".join(f"**{get_display_name(u)}**" for u in longest_runners)
        longest_block = f"Longest run: **{longest_duration_text}**\nParticipants: {longest_participants}\n\n"
    else:
        longest_block = ""

    attempt_number = len(team_accuracy_history[current_run_team]) if current_run_team in team_accuracy_history else 1

    embed = discord.Embed(
        title=f"**{current_run_team.upper() if current_run_team else 'NO TEAM'}'S ATTEMPT #{attempt_number} STATS:**",
        description=(
            f"Fastest 1-hour run: **{best_1hour:,}**\n"
            f"Participants: {best_participants_display}\n\n"
            f"{longest_block}"
            f"Correct Rate: **{accuracy_text}**\n"
            f"✅ **{correct:,}**\n"
            f"❌ **{incorrect:,}**\n\n"
            f"{leaderboard_text}"
        ),
        color=0xCCA958
    )

    await interaction.response.send_message(embed=embed)

    # clear run-only state
    async with counts_lock:
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
        run_timer_task = None
        run_sampler_task = None

@bot.tree.command(name="top_users", description="Shows total numbers counted by each user and which team they belong to.")
async def leaderboard_users(interaction: discord.Interaction):
    async with counts_lock:
        items = sorted(
            total_counts_by_user.items(),
            key=lambda x: -x[1]
        )

    if not items:
        await interaction.response.send_message(
            "No data available yet.",
            ephemeral=False
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
    entries = []
    async with counts_lock:
        for team, runs in team_accuracy_history.items():
            for idx, run in enumerate(runs, start=1):
                acc = run.get("accuracy")
                if acc is None:
                    continue
                entries.append((team, idx, float(acc)))

    if not entries:
        await interaction.response.send_message("No accuracy data available yet.")
        return

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
    entries = []
    async with counts_lock:
        for team, runs in team_accuracy_history.items():
            for idx, run in enumerate(runs, start=1):
                count = int(run.get("correct", 0))
                entries.append((team, idx, count))

    if not entries:
        await interaction.response.send_message("No run data available yet.")
        return

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

    entries.sort(key=lambda x: -x[2])

    lines = []
    for rank, (team, attempt, best, top_users) in enumerate(entries, start=1):
        if top_users:
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

@bot.tree.command(name="leaderboard_longest", description="Shows longest two-person runs across attempts.")
async def leaderboard_longest(interaction: discord.Interaction):
    entries = []
    async with counts_lock:
        for team, runs in team_accuracy_history.items():
            for idx, run in enumerate(runs, start=1):
                two_runs = run.get("two_person_runs", []) or []
                for rec in two_runs:
                    dur = int(rec.get("duration", 0))
                    runners = rec.get("runners", ())
                    names = [get_display_name(u) for u in runners]
                    runners_display = " & ".join(names[:2])
                    entries.append((dur, team, idx, runners_display))

    if not entries:
        await interaction.response.send_message("No two-person run data available yet.")
        return

    entries.sort(key=lambda x: -x[0])

    lines = []
    for rank, (dur, team, attempt_idx, runners_display) in enumerate(entries, start=1):
        dur_text = format_duration_hours_minutes(dur)
        lines.append(f"**#{rank}** {runners_display} - {team}, **{dur_text}** hours")

    embed = discord.Embed(
        title="**LONGEST RUN LEADERBOARD**",
        description="\n".join(lines),
        color=0xCCA958
    )

    await interaction.response.send_message(embed=embed)

# -------- NEW: /points command --------
@bot.tree.command(name="points", description="Shows points leaderboard from current winners of categories.")
async def points_command(interaction: discord.Interaction):
    """
    Calculates points from current winners of:
      - Fastest Run (1 point)
      - Numbers Counted (2 points)
      - Accuracy (1 point)
      - Longest Run (1 point)

    Displays teams sorted by points, listing categories they currently lead and their total points.
    """
    # compute winners for each category
    fastest_winner = None
    numbers_winner = None
    accuracy_winner = None
    longest_winner = None

    async with counts_lock:
        # Fastest Run winner: highest best_1hour across all team attempts
        fastest_entries = []
        for team, runs in team_accuracy_history.items():
            for idx, run in enumerate(runs, start=1):
                best = int(run.get("best_1hour", 0) or 0)
                if best > 0:
                    fastest_entries.append((best, team, idx))
        if fastest_entries:
            fastest_entries.sort(key=lambda x: -x[0])
            fastest_winner = fastest_entries[0][1]

        # Numbers Counted winner: highest correct count across attempts
        numbers_entries = []
        for team, runs in team_accuracy_history.items():
            for idx, run in enumerate(runs, start=1):
                correct = int(run.get("correct", 0) or 0)
                if correct > 0:
                    numbers_entries.append((correct, team, idx))
        if numbers_entries:
            numbers_entries.sort(key=lambda x: -x[0])
            numbers_winner = numbers_entries[0][1]

        # Accuracy winner: highest accuracy percent across attempts
        accuracy_entries = []
        for team, runs in team_accuracy_history.items():
            for idx, run in enumerate(runs, start=1):
                acc = run.get("accuracy")
                if acc is None:
                    continue
                accuracy_entries.append((float(acc), team, idx))
        if accuracy_entries:
            accuracy_entries.sort(key=lambda x: -x[0])
            accuracy_winner = accuracy_entries[0][1]

        # Longest Run winner: highest duration from two_person_runs across attempts
        longest_entries = []
        for team, runs in team_accuracy_history.items():
            for idx, run in enumerate(runs, start=1):
                two_runs = run.get("two_person_runs", []) or []
                for rec in two_runs:
                    dur = int(rec.get("duration", 0) or 0)
                    if dur > 0:
                        longest_entries.append((dur, team, idx))
        if longest_entries:
            longest_entries.sort(key=lambda x: -x[0])
            longest_winner = longest_entries[0][1]

    # tally points
    points = defaultdict(int)
    winning_categories = defaultdict(list)

    if fastest_winner:
        points[fastest_winner] += 1
        winning_categories[fastest_winner].append("Fastest Run")
    if numbers_winner:
        points[numbers_winner] += 2  # Numbers Counted worth 2 points
        winning_categories[numbers_winner].append("Numbers Counted")
    if accuracy_winner:
        points[accuracy_winner] += 1
        winning_categories[accuracy_winner].append("Accuracy")
    if longest_winner:
        points[longest_winner] += 1
        winning_categories[longest_winner].append("Longest Run")

    if not points:
        await interaction.response.send_message("No winners available yet to calculate points.")
        return

    # build sorted leaderboard by points desc, then team name
    leaderboard = sorted(points.items(), key=lambda x: (-x[1], x[0]))

    lines = []
    for i, (team, pts) in enumerate(leaderboard, start=1):
        cats = ", ".join(winning_categories.get(team, []))
        if cats:
            lines.append(f"**#{i}** {team} - {cats}, **{pts}**")
        else:
            lines.append(f"**#{i}** {team}, **{pts}**")

    embed = discord.Embed(
        title="**POINTS LEADERBOARD**",
        description="\n".join(lines),
        color=0xCCA958
    )

    await interaction.response.send_message(embed=embed)

# -------- NEW: /all_runs command --------
@bot.tree.command(name="all_runs", description="Shows summary of all saved runs (per team attempts).")
async def all_runs(interaction: discord.Interaction):
    """
    Displays all saved runs in order (per team, in the order they were stored).
    For each attempt shows:
      - Numbers Counted (correct)
      - Accuracy (formatted)
      - Longest Run (HH:MM:SS)
      - Fastest Run (best 1-hour)
    """
    entries = []
    async with counts_lock:
        # iterate teams in insertion order and their attempts in stored order
        for team, runs in team_accuracy_history.items():
            for idx, run in enumerate(runs, start=1):
                correct = int(run.get("correct", 0) or 0)
                acc = run.get("accuracy")
                if acc is None:
                    acc_text = "N/A"
                else:
                    acc_text = "100%" if acc == 100 else f"{float(acc):06.3f}%"
                # longest run (max duration in two_person_runs)
                two_runs = run.get("two_person_runs", []) or []
                longest_secs = 0
                for rec in two_runs:
                    dur = int(rec.get("duration", 0) or 0)
                    if dur > longest_secs:
                        longest_secs = dur
                longest_text = format_duration(longest_secs) if longest_secs > 0 else "N/A"
                best_1hour = int(run.get("best_1hour", 0) or 0)
                entries.append({
                    "team": team,
                    "attempt": idx,
                    "correct": correct,
                    "accuracy": acc_text,
                    "longest": longest_text,
                    "fastest": best_1hour
                })

    if not entries:
        await interaction.response.send_message("No saved runs available yet.")
        return

    # build the message string
    blocks = []
    for e in entries:
        team_label = e["team"].upper()
        blocks.append(f"{team_label} #{e['attempt']} ATTEMPT")
        blocks.append(f"Numbers Counted: **{e['correct']:,}**")
        blocks.append(f"Accuracy **{e['accuracy']}**")
        blocks.append(f"Longest Run: **{e['longest']}**")
        blocks.append(f"Fastest Run: **{e['fastest']:,}**")
        blocks.append("")  # blank line between attempts

    desc = "\n".join(blocks).strip()

    embed = discord.Embed(
        title="**ALL SAVED RUNS**",
        description=desc,
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
