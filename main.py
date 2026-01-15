import os
import asyncio
import logging
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime, timezone

# ---------- ENV ----------
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------- LOGGING ----------
handler = logging.FileHandler("discord.log", encoding="utf-8", mode="w")

# ---------- DISCORD ----------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- CONFIG ----------
TRACKED_CHANNELS = {
    1060539711871004734,
    987737957530239026
}

RUN_DURATION = 30  # change to 86400 later

current_run_id = None
run_lock = asyncio.Lock()

# ---------- EVENTS ----------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

@bot.event
async def on_message(message: discord.Message):
    global current_run_id

    if message.author.bot or not current_run_id:
        return
    if message.channel.id not in TRACKED_CHANNELS:
        return

    content = (message.content or "").lstrip()
    if not content or not content[0].isdigit():
        return

    async with run_lock:
        supabase.table("run_user_counts").upsert(
            {
                "run_id": current_run_id,
                "user_id": message.author.id,
                "count": 1
            },
            on_conflict="run_id,user_id"
        ).execute()

# ---------- COMMANDS ----------
@bot.tree.command(name="start_run", description="Starts the 24 hours run in both channels.")
async def start_run(interaction: discord.Interaction):
    global current_run_id

    active = supabase.table("runs").select("*").eq("active", True).execute().data
    if active:
        await interaction.response.send_message("A run is already active.", ephemeral=True)
        return

    run = supabase.table("runs").insert(
        {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "active": True
        }
    ).execute().data[0]

    current_run_id = run["id"]

    await interaction.response.send_message(
        "Run started! Stats are now being collected for the next 24 hours."
    )

    await asyncio.sleep(RUN_DURATION)

    supabase.table("runs").update(
        {
            "active": False,
            "ended_at": datetime.now(timezone.utc).isoformat()
        }
    ).eq("id", current_run_id).execute()

    # USER LEADERBOARD
    data = supabase.table("run_user_counts").select("*").eq(
        "run_id", current_run_id
    ).execute().data

    data.sort(key=lambda x: -x["count"])

    embed = discord.Embed(title="**USER COUNTS**", color=discord.Color.blue())

    if not data:
        embed.description = "No numbers were counted."
    else:
        lines = []
        for i, row in enumerate(data, 1):
            member = interaction.guild.get_member(row["user_id"])
            name = member.nick if member and member.nick else member.name if member else "Unknown"
            lines.append(f"#{i} {name}, {row['count']}")
        embed.description = "\n".join(lines)

    await interaction.followup.send("Run ended!", embed=embed)
    current_run_id = None


@bot.tree.command(name="leaderboard_numbers", description="Shows the runs with most numbers counted.")
async def leaderboard_numbers(interaction: discord.Interaction):
    runs = supabase.rpc("run_totals").execute().data

    embed = discord.Embed(title="**NUMBERS COUNTED**", color=discord.Color.gold())

    if not runs:
        embed.description = "No runs recorded yet."
    else:
        lines = []
        for i, run in enumerate(runs, 1):
            lines.append(f"**#{i}** Run {run['run_id']}, **{run['total']}**")
        embed.description = "\n".join(lines)

    await interaction.response.send_message(embed=embed)

# ---------- START ----------
bot.run(DISCORD_TOKEN, log_handler=handler)
