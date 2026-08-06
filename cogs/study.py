import discord
from discord import app_commands
from discord.ext import commands


class AdminCog(commands.Cog, name="Admin"):
    def __init__(self, bot):
        self.bot = bot

    # ==================== BASIC EMBED ====================

    @app_commands.command(
        name="embed", description="Create and send a custom embed (Admin only)"
    )
    @app_commands.describe(
        title="Embed title",
        description="Main embed description",
        color="Color in hex (e.g. ff6600)",
        footer="Footer text (optional)",
    )
    @app_commands.default_permissions(administrator=True)
    async def create_embed(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        color: str = "ff6600",
        footer: str = None,
    ):
        try:
            color_int = int(color, 16)
        except ValueError:
            color_int = 0xFF6600  # default orange

        embed = discord.Embed(title=title, description=description, color=color_int)

        if footer:
            embed.set_footer(text=footer)

        embed.timestamp = discord.utils.utcnow()
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url,
        )

        await interaction.response.send_message(embed=embed)

    # ==================== ANNOUNCEMENT EMBED ====================

    @app_commands.command(name="announce", description="Send an announcement embed")
    @app_commands.describe(message="Announcement text", ping="Ping @everyone? (yes/no)")
    @app_commands.default_permissions(administrator=True)
    async def announce(
        self, interaction: discord.Interaction, message: str, ping: str = "no"
    ):
        embed = discord.Embed(
            title="🔺 Pi-space Announcement", description=message, color=0xFF6600
        )
        embed.set_footer(text=f"Announced by {interaction.user}")

        if ping.lower() in ["yes", "true", "1"]:
            content = "@everyone"
        else:
            content = None

        await interaction.response.send_message(content=content, embed=embed)

    # ==================== DM WITH EMBED ====================

    @app_commands.command(name="dm", description="Send a DM with embed to a user")
    @app_commands.describe(
        user="User to message", title="Embed title", description="Embed description"
    )
    @app_commands.default_permissions(administrator=True)
    async def dm_embed(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        title: str,
        description: str,
    ):
        embed = discord.Embed(title=title, description=description, color=0xFF6600)
        embed.set_footer(text=f"From Pi-space Bot • {interaction.guild.name}")

        try:
            await user.send(embed=embed)
            await interaction.response.send_message(
                f"✅ Embed DM sent to **{user}**", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ User has DMs disabled or blocked the bot.", ephemeral=True
            )
        except Exception:
            await interaction.response.send_message(
                "❌ Failed to send DM.", ephemeral=True
            )

    # ==================== SIMPLE SAY ====================

    @app_commands.command(name="say", description="Simple message in channel")
    @app_commands.default_permissions(administrator=True)
    async def say(self, interaction: discord.Interaction, message: str):
        await interaction.channel.send(message)
        await interaction.response.send_message("✅ Sent!", ephemeral=True)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
