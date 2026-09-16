from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from utils import load_data, save_data


def _profile_key(profiles: dict, requested_name: str) -> str | None:
    normalized = requested_name.strip().casefold()
    return next(
        (name for name in profiles if name.strip().casefold() == normalized),
        None,
    )


def _clean_members(info: dict) -> list[int]:
    members = info.setdefault("members", [])
    info["members"] = list(dict.fromkeys(members))
    return info["members"]


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
        name = name.strip()
        description = description.strip()
        if not name:
            await interaction.followup.send("❌ Profile name cannot be empty.", ephemeral=True)
            return
        if len(name) > 80 or len(description) > 1000:
            await interaction.followup.send(
                "❌ Profile names must be 80 characters or fewer and descriptions 1000 characters or fewer.",
                ephemeral=True,
            )
            return
        data = load_data()
        profiles = data.setdefault("profiles", {})

        if _profile_key(profiles, name):
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
        name="editprofile", description="Admin: Rename or update a study profile"
    )
    @app_commands.describe(
        name="Current profile name",
        new_name="New profile name; leave blank to keep the current name",
        description="New short description",
    )
    @app_commands.default_permissions(administrator=True)
    async def edit_profile(
        self,
        interaction: discord.Interaction,
        name: str,
        new_name: str = "",
        description: str = "",
    ):
        await interaction.response.defer(ephemeral=True)
        data = load_data()
        profiles = data.setdefault("profiles", {})
        profile_key = _profile_key(profiles, name)
        if profile_key is None:
            await interaction.followup.send("❌ Profile not found.", ephemeral=True)
            return

        updated_name = new_name.strip() or profile_key
        updated_description = description.strip()
        if len(updated_name) > 80 or len(updated_description) > 1000:
            await interaction.followup.send(
                "❌ Profile names must be 80 characters or fewer and descriptions 1000 characters or fewer.",
                ephemeral=True,
            )
            return
        existing_key = _profile_key(profiles, updated_name)
        if existing_key and existing_key != profile_key:
            await interaction.followup.send("❌ That profile name already exists.", ephemeral=True)
            return

        info = profiles.pop(profile_key)
        if new_name.strip():
            profiles[updated_name] = info
            for user_key, selected in data.setdefault("user_profiles", {}).items():
                if selected == profile_key:
                    data["user_profiles"][user_key] = updated_name
        else:
            profiles[profile_key] = info
        if description.strip():
            info["description"] = updated_description
        save_data(data)
        await interaction.followup.send(f"✅ Profile '{updated_name}' updated.", ephemeral=True)

    @app_commands.command(name="removeprofile", description="Admin: Remove a study profile")
    @app_commands.describe(name="Profile name to remove")
    @app_commands.default_permissions(administrator=True)
    async def remove_profile(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        data = load_data()
        profiles = data.setdefault("profiles", {})
        profile_key = _profile_key(profiles, name)
        if profile_key is None:
            await interaction.followup.send("❌ Profile not found.", ephemeral=True)
            return
        profiles.pop(profile_key)
        user_profiles = data.setdefault("user_profiles", {})
        removed_users = [
            user_key for user_key, selected in user_profiles.items() if selected == profile_key
        ]
        for user_key in removed_users:
            user_profiles.pop(user_key, None)
        save_data(data)
        await interaction.followup.send(
            f"✅ Profile '{profile_key}' removed. {len(removed_users)} member selection(s) cleared.",
            ephemeral=True,
        )

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
        for nm, info in list(profiles.items())[:25]:
            desc = info.get("description", "") or "No description."
            count = len(_clean_members(info))
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

        profile_key = _profile_key(profiles, name)
        if profile_key is None:
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
        user_profiles[user_key] = profile_key
        members = _clean_members(profiles[profile_key])
        if interaction.user.id not in members:
            members.append(interaction.user.id)

        save_data(data)
        await interaction.followup.send(
            f"✅ Your profile has been set to **{profile_key}**.", ephemeral=True
        )

    @app_commands.command(name="clearprofile", description="Clear your current study profile")
    async def clear_profile(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        data = load_data()
        user_key = str(interaction.user.id)
        selected = data.setdefault("user_profiles", {}).pop(user_key, None)
        if selected:
            profiles = data.setdefault("profiles", {})
            if selected in profiles:
                members = _clean_members(profiles[selected])
                profiles[selected]["members"] = [
                    member_id for member_id in members if member_id != interaction.user.id
                ]
            save_data(data)
        await interaction.followup.send(
            "✅ Your study profile has been cleared." if selected else "You do not have a study profile set.",
            ephemeral=True,
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
        profile_key = _profile_key(profiles, profile)
        if profile_key is None:
            await interaction.response.send_message(
                "Your saved profile no longer exists. Use /setprofile.", ephemeral=True
            )
            return
        info = profiles[profile_key]
        desc = info.get("description", "No description.")
        count = len(_clean_members(info))

        embed = discord.Embed(title=f"Your Profile — {profile_key}", color=0x00FF88)
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

        profile_key = _profile_key(profiles, profile)
        if profile_key is None:
            await interaction.followup.send("Profile not found.", ephemeral=True)
            return

        members = _clean_members(profiles[profile_key])
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
            title=f"Matches — {profile_key}", description=display, color=0xFF6600
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ProfileCog(bot))
