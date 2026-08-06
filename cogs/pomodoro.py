import asyncio

import discord
from discord import app_commands
from discord.ext import commands


class PomodoroCog(commands.Cog, name="Pomodoro"):
    def __init__(self, bot):
        self.bot = bot
        self.active_timers = {}  # user_id: {"channel": voice_channel, "task": message}

    @app_commands.command(
        name="pomodoro", description="Start Pomodoro and join your voice channel"
    )
    @app_commands.describe(minutes="Duration in minutes (default 25)")
    async def start_pomodoro(self, interaction: discord.Interaction, minutes: int = 25):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "❌ You must be in a voice channel first!", ephemeral=True
            )
            return

        voice_channel = interaction.user.voice.channel

        # Join the voice channel
        try:
            vc = await voice_channel.connect()
            await interaction.response.send_message(
                f"🍅 **Pomodoro Started** ({minutes} min) — Joined **{voice_channel.name}** 🔺"
            )
        except Exception:
            await interaction.response.send_message(
                "❌ Could not join voice channel.", ephemeral=True
            )
            return

        self.active_timers[interaction.user.id] = {"vc": vc, "channel": voice_channel}

        # Timer
        await asyncio.sleep(minutes * 60)

        # Finish
        await interaction.followup.send(
            f"⏰ **Pomodoro Finished!** Great session {interaction.user.mention}!"
        )

        # Leave voice after session
        if vc.is_connected():
            await vc.disconnect()

        if interaction.user.id in self.active_timers:
            del self.active_timers[interaction.user.id]

    @app_commands.command(
        name="stoppomo", description="Stop current Pomodoro and leave voice"
    )
    async def stop_pomodoro(self, interaction: discord.Interaction):
        if interaction.user.id not in self.active_timers:
            await interaction.response.send_message(
                "No active Pomodoro session found.", ephemeral=True
            )
            return

        vc = self.active_timers[interaction.user.id]["vc"]
        if vc.is_connected():
            await vc.disconnect()

        del self.active_timers[interaction.user.id]
        await interaction.response.send_message(
            "🛑 Pomodoro stopped and left voice channel."
        )


async def setup(bot):
    await bot.add_cog(PomodoroCog(bot))
