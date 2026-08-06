"""Main entrypoint for the Pi-space Discord bot.

Initialises the bot, loads cogs from the `cogs` package, and defines
core event handlers such as startup sync and DM forwarding.
"""

import asyncio
import os
import pathlib

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.dm_messages = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


async def load_cogs():
    """Load only the selected cog modules for this deployment.

    This prevents commands defined in unlisted cogs from being registered.
    """
    allowed_cogs = {"admin", "lessons", "planner", "pomodoro", "profile"}
    cogs_dir = pathlib.Path(__file__).parent / "cogs"
    if not cogs_dir.exists():
        print("⚠️ cogs folder not found!")
        return

    for cog_file in cogs_dir.glob("*.py"):
        if cog_file.name.startswith("_"):
            continue
        if cog_file.stem not in allowed_cogs:
            print(f"⏭ Skipping cog: {cog_file.stem}")
            continue

        cog_name = f"cogs.{cog_file.stem}"
        try:
            await bot.load_extension(cog_name)
            print(f"✅ Loaded cog: {cog_file.stem}")
        except Exception as e:
            print(f"❌ Failed to load {cog_file.stem}: {e}")


@bot.event
async def on_ready():
    """Bot ready event handler.

    Performs optional guild-specific command sync when `DEV_GUILD_ID`
    is set, otherwise performs a global sync. Caches a DM log channel
    lookup for later use by the DM forwarding handler.
    """
    print(f"\n🔺 Pi-space is online as {bot.user}")
    try:
        # Fast-sync to a development guild if provided for immediate command availability.
        dev_gid = os.getenv("DEV_GUILD_ID")
        if dev_gid:
            try:
                guild_obj = discord.Object(id=int(dev_gid))
                synced = await bot.tree.sync(guild=guild_obj)
                print(f"✅ Synced {len(synced)} guild commands to {dev_gid}")
            except Exception as eg:
                print(f"Guild sync failed: {eg}. Falling back to global sync.")
                synced = await bot.tree.sync()
                print(f"✅ Synced {len(synced)} global slash commands")
        else:
            synced = await bot.tree.sync()
            print(f"✅ Synced {len(synced)} global slash commands")
    except Exception as e:
        print(f"Sync warning: {e}")
    # Cache commonly used channels to avoid scanning on each DM
    bot.dm_log_channel = discord.utils.get(bot.get_all_channels(), name="bot-dms")


# ==================== DM FORWARDING ====================
@bot.event
async def on_message(message):
    """Handle incoming messages.

    For DMs (non-bot authors) forward the content into the configured
    `#bot-dms` channel and reply to the user with a short acknowledgement.
    Non-DM messages are passed through to command processing.
    """
    if message.guild is None and not message.author.bot:  # DM received
        # Forward to your private channel (cached lookup)
        log_channel = getattr(bot, "dm_log_channel", None)
        if log_channel is None:
            log_channel = discord.utils.get(bot.get_all_channels(), name="bot-dms")
            bot.dm_log_channel = log_channel

        if log_channel:
            embed = discord.Embed(
                title="📩 New DM Received",
                description=message.content,
                color=0xFF6600,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_author(
                name=str(message.author), icon_url=message.author.display_avatar.url
            )
            embed.add_field(name="User ID", value=message.author.id, inline=True)
            await log_channel.send(embed=embed)
        else:
            print(
                f"⚠️ DM received from {message.author} but no #bot-dms channel found."
            )

        # Reply to the user
        reply_embed = discord.Embed(
            title="🔺 Pi-space Bot",
            description="I received your message! How can I help you today?",
            color=0xFF6600,
        )
        await message.channel.send(embed=reply_embed)

    await bot.process_commands(message)


async def main():
    """Start the bot after loading cogs and reading the token from env.

    Uses an async context manager for `bot` so resources are cleaned up
    on shutdown.
    """
    async with bot:
        await load_cogs()
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            print("❌ DISCORD_TOKEN not found in .env!")
            return
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
