from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from utils import load_data, save_data


class ProfileCog(commands.Cog, name="Profiles"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="addprofile", description="Admin: Add a study profile (e.g. Mathematics)"
    )
    @app_commands.describe(name="Profile name", description="Short description")
    @app_commands.default_permissions(administrator=True)
    async def add_profile(
        self, interaction: discord.Interaction, name: str, description: str = ""
    ):
        await interaction.response.defer(ephemeral=True)
        data = load_data()
        profiles = data.setdefault("profiles", {})

        if name in profiles:
            await interaction.followup.send(
                f"❌ Profile '{name}' already exists.", ephemeral=True
            )
            return

        profiles[name] = {
            "description": description,
            "created": datetime.now().isoformat(),
            "created_by": interaction.user.id,
            "members": [],
        }
        save_data(data)
        await interaction.followup.send(f"✅ Profile '{name}' created.", ephemeral=True)

    @app_commands.command(
        name="listprofiles", description="List available study profiles"
    )
    async def list_profiles(self, interaction: discord.Interaction):
        data = load_data()
        profiles = data.get("profiles", {})
        if not profiles:
            await interaction.response.send_message(
                "No profiles defined yet.", ephemeral=True
            )
            return

        embed = discord.Embed(title="Available Profiles", color=0xFF6600)
        for nm, info in profiles.items():
            desc = info.get("description", "") or "No description."
            count = len(info.get("members", []))
            embed.add_field(name=f"{nm} ({count})", value=desc, inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="setprofile",
        description="Set your study profile (choose from admin-defined profiles)",
    )
    @app_commands.describe(name="Profile name")
    async def set_profile(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        data = load_data()
        profiles = data.get("profiles", {})

        if name not in profiles:
            await interaction.followup.send(
                "❌ Profile not found. Use /listprofiles to see available profiles.",
                ephemeral=True,
            )
            return

        user_key = str(interaction.user.id)
        user_profiles = data.setdefault("user_profiles", {})
        old = user_profiles.get(user_key)

        # remove from old profile members
        if old and old in profiles:
            try:
                profiles[old]["members"].remove(interaction.user.id)
            except ValueError:
                pass

        # set new
        user_profiles[user_key] = name
        if interaction.user.id not in profiles[name]["members"]:
            profiles[name]["members"].append(interaction.user.id)

        save_data(data)
        await interaction.followup.send(
            f"✅ Your profile has been set to **{name}**.", ephemeral=True
        )

    @app_commands.command(name="myprofile", description="Show your current profile")
    async def my_profile(self, interaction: discord.Interaction):
        data = load_data()
        user_profiles = data.get("user_profiles", {})
        profile = user_profiles.get(str(interaction.user.id))
        if not profile:
            await interaction.response.send_message(
                "You don't have a profile set. Use /setprofile.", ephemeral=True
            )
            return

        profiles = data.get("profiles", {})
        info = profiles.get(profile, {})
        desc = info.get("description", "No description.")
        count = len(info.get("members", []))

        embed = discord.Embed(title=f"Your Profile — {profile}", color=0x00FF88)
        embed.add_field(name="Description", value=desc, inline=False)
        embed.add_field(name="Members", value=str(count), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="findmatches", description="Find members who share a profile"
    )
    @app_commands.describe(
        profile="Optional profile name; if omitted, uses your profile"
    )
    async def find_matches(self, interaction: discord.Interaction, profile: str = None):
        await interaction.response.defer(ephemeral=True)
        data = load_data()
        profiles = data.get("profiles", {})

        if not profile:
            profile = data.get("user_profiles", {}).get(str(interaction.user.id))
            if not profile:
                await interaction.followup.send(
                    "You don't have a profile set. Provide a profile name or use /setprofile.",
                    ephemeral=True,
                )
                return

        if profile not in profiles:
            await interaction.followup.send("Profile not found.", ephemeral=True)
            return

        members = profiles[profile].get("members", [])
        if not members:
            await interaction.followup.send(
                "No members found for this profile.", ephemeral=True
            )
            return

        # Resolve member display names where possible
        names = []
        guild = interaction.guild
        for uid in members:
            try:
                member = guild.get_member(uid) if guild else None
                if not member and guild:
                    member = await guild.fetch_member(uid)
                if member:
                    names.append(str(member))
                else:
                    names.append(f"<@{uid}>")
            except Exception:
                names.append(f"<@{uid}>")

        # avoid extremely long messages
        display = "\n".join(names[:50])
        if len(names) > 50:
            display += f"\n...and {len(names)-50} more"

        embed = discord.Embed(
            title=f"Matches — {profile}", description=display, color=0xFF6600
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ProfileCog(bot))
