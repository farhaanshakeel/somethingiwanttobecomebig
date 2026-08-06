"""Admin and study-group related commands and helpers.

Provides commands to create, list, join, and manage study groups.
The cog handles workspace channel creation and member permissions.
"""

from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from utils import load_data, save_data


class StudyCog(commands.Cog, name="Study"):
    """Cog exposing study-group management commands.

    Commands include group creation, listing, joining, and admin-only
    cleanup utilities. The cog takes care of creating text/voice
    workspaces and setting permissions.
    """

    def __init__(self, bot):
        self.bot = bot

    async def _create_group_workspace(
        self, interaction: discord.Interaction, name: str
    ):
        """Create category, text and voice channels for a study group.

        Returns a dict with the IDs of the created category, text, and
        voice channels (or None values if creation failed).
        """
        guild = interaction.guild
        if guild is None:
            return {}

        category_name = f"Study - {name}"
        everyone = guild.default_role
        manager_overwrites = {
            everyone: discord.PermissionOverwrite(
                view_channel=False, read_messages=False, connect=False, speak=False
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_messages=True,
                connect=True,
                speak=True,
            ),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_messages=True,
                connect=True,
                speak=True,
            ),
        }

        category = discord.utils.get(guild.categories, name=category_name)
        if category is None:
            try:
                category = await guild.create_category(
                    category_name,
                    overwrites=manager_overwrites,
                    reason="Auto-created study group category",
                )
            except Exception:
                category = None
        else:
            try:
                await category.edit(overwrites=manager_overwrites)
            except Exception:
                pass

        text_name = name.lower().replace(" ", "-")[:90]
        voice_name = f"{name} voice"[:90]
        text_channel = None
        voice_channel = None

        if category:
            text_channel = discord.utils.get(category.text_channels, name=text_name)
            if text_channel is None:
                try:
                    text_channel = await guild.create_text_channel(
                        text_name,
                        category=category,
                        overwrites=manager_overwrites,
                        reason="Study group text channel",
                    )
                except Exception:
                    text_channel = None

            voice_channel = discord.utils.get(category.voice_channels, name=voice_name)
            if voice_channel is None:
                try:
                    voice_channel = await guild.create_voice_channel(
                        voice_name,
                        category=category,
                        overwrites=manager_overwrites,
                        reason="Study group voice channel",
                    )
                except Exception:
                    voice_channel = None

        return {
            "category_id": category.id if category else None,
            "text_channel_id": text_channel.id if text_channel else None,
            "voice_channel_id": voice_channel.id if voice_channel else None,
        }

    async def _allow_member_access(
        self, interaction: discord.Interaction, group: dict, member: discord.Member
    ):
        """Grant view/send/connect permissions to `member` for the group's workspace.

        This attempts to look up the stored channel IDs and update permissions
        so the member can access the text and voice hubs for the group.
        """
        guild = interaction.guild
        if guild is None:
            return

        text_channel = (
            guild.get_channel(group.get("workspace_text"))
            if group.get("workspace_text")
            else None
        )
        voice_channel = (
            guild.get_channel(group.get("workspace_voice"))
            if group.get("workspace_voice")
            else None
        )

        if text_channel:
            try:
                await text_channel.set_permissions(
                    member, view_channel=True, send_messages=True, read_messages=True
                )
            except Exception:
                pass
        if voice_channel:
            try:
                await voice_channel.set_permissions(
                    member, view_channel=True, connect=True, speak=True
                )
            except Exception:
                pass

    @app_commands.command(name="studygroup", description="Create a new study group")
    @app_commands.describe(
        name="Group name",
        description="Optional description",
        capacity="Maximum number of members (0 for infinite, max 20)",
    )
    async def create_group(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str = None,
        capacity: int = 20,
    ):
        data = load_data()
        if name in data["study_groups"]:
            await interaction.response.send_message(
                "❌ This group already exists!", ephemeral=True
            )
            return

        if capacity < 0:
            capacity = 0
        if capacity > 20:
            capacity = 20

        # Determine if creator is an administrator; admin-created groups are marked.
        is_admin = False
        try:
            is_admin = interaction.user.guild_permissions.administrator
        except Exception:
            is_admin = False

        # Prevent more than one admin-started group
        if is_admin:
            for g in data.get("study_groups", {}).values():
                if g.get("admin_started"):
                    await interaction.response.send_message(
                        "❌ An admin-started study group already exists — only one admin group is allowed.",
                        ephemeral=True,
                    )
                    return

        workspace = await self._create_group_workspace(interaction, name)
        data["study_groups"][name] = {
            "owner": interaction.user.id,
            "members": [interaction.user.id],
            "description": description or "No description provided.",
            "created": datetime.now().isoformat(),
            "admin_started": bool(is_admin),
            "capacity": capacity,
            "duration": "5 months",
            "workspace_category": workspace.get("category_id"),
            "workspace_text": workspace.get("text_channel_id"),
            "workspace_voice": workspace.get("voice_channel_id"),
        }
        save_data(data)

        # Beautiful Embed
        embed = discord.Embed(
            title=f"🔺 {name}",
            description=description
            or "A new study group has been successfully created.",
            color=0xFF6600,
        )
        embed.add_field(name="Owner", value=interaction.user.mention, inline=True)
        embed.add_field(name="Members", value="1 (You)", inline=True)
        embed.add_field(
            name="Created", value=datetime.now().strftime("%d %B %Y"), inline=True
        )
        embed.set_footer(text="Pi-space • Study Together")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="listgroups", description="List all study groups")
    async def list_groups(self, interaction: discord.Interaction):
        data = load_data()
        groups = data.get("study_groups", {})

        if not groups:
            await interaction.response.send_message("No study groups created yet.")
            return
        # Show each group as an embed card with a Join button
        await interaction.response.defer()

        for name, info in groups.items():
            owner_id = info.get("owner")
            owner_mention = f"<@{owner_id}>" if owner_id else "Unknown"
            members = info.get("members", [])
            count = len(members)
            admin_started = info.get("admin_started", False)

            embed = discord.Embed(
                title=f"{name}", description=info.get("description", ""), color=0x2F3136
            )
            embed.add_field(name="Leader", value=owner_mention, inline=True)
            embed.add_field(
                name="Subject Track", value=info.get("subject", "General"), inline=True
            )
            embed.add_field(
                name="Duration / Lifespan",
                value=info.get("duration", "N/A"),
                inline=True,
            )
            topics = info.get("topics")
            if topics:
                embed.add_field(
                    name="Target Topics & Goals",
                    value="\n".join(topics[:6]),
                    inline=False,
                )
            capacity = info.get("capacity", 20)
            capacity_label = "∞" if capacity == 0 else str(capacity)
            embed.add_field(
                name="Vacancies", value=f"{count}/{capacity_label} members", inline=True
            )
            if capacity != 0 and count >= capacity:
                embed.add_field(name="Status", value="⛔ Full", inline=True)
            text_id = info.get("workspace_text")
            voice_id = info.get("workspace_voice")
            if text_id:
                embed.add_field(name="Text Hub", value=f"<#{text_id}>", inline=True)
            if voice_id:
                embed.add_field(name="Voice Hub", value=f"<#{voice_id}>", inline=True)
            embed.set_footer(
                text=("Official Admin Group" if admin_started else "Peer-led Group")
            )

            # Interactive view with Join button
            class GroupView(discord.ui.View):
                def __init__(self, author_id: int):
                    super().__init__(timeout=None)
                    self.author_id = author_id

                @discord.ui.button(
                    label="Join Study Group →", style=discord.ButtonStyle.primary
                )
                async def join_button(
                    self, button_inter: discord.Interaction, button: discord.ui.Button
                ):
                    # Reload latest group state
                    data_local = load_data()
                    grp = data_local.get("study_groups", {}).get(name)
                    if grp is None:
                        await button_inter.response.send_message(
                            "❌ Group no longer exists.", ephemeral=True
                        )
                        return

                    if button_inter.user.id in grp.get("members", []):
                        await button_inter.response.send_message(
                            "You're already in this group.", ephemeral=True
                        )
                        return

                    capacity = grp.get("capacity", 20)
                    if capacity != 0 and len(grp.get("members", [])) >= capacity:
                        await button_inter.response.send_message(
                            "❌ This study group is full.", ephemeral=True
                        )
                        return

                    if not grp.get("admin_started"):
                        # enforce terms agreement before joining peer-led groups
                        class ConfirmPeerView(discord.ui.View):
                            def __init__(self, user_id: int):
                                super().__init__(timeout=60)
                                self.user_id = user_id

                            async def interaction_check(
                                self, inter: discord.Interaction
                            ) -> bool:
                                return inter.user.id == self.user_id

                            @discord.ui.button(
                                label="Agree and Join",
                                style=discord.ButtonStyle.success,
                            )
                            async def confirm(
                                self, i: discord.Interaction, b: discord.ui.Button
                            ):
                                dl = load_data()
                                g = dl.get("study_groups", {}).get(name)
                                if g is None:
                                    await i.response.edit_message(
                                        content="❌ Group no longer exists.",
                                        embed=None,
                                        view=None,
                                    )
                                    return
                                if i.user.id in g.get("members", []):
                                    await i.response.edit_message(
                                        content="You're already in this group.",
                                        embed=None,
                                        view=None,
                                    )
                                    return
                                capacity = g.get("capacity", 20)
                                if (
                                    capacity != 0
                                    and len(g.get("members", [])) >= capacity
                                ):
                                    await i.response.edit_message(
                                        content="❌ This study group is full.",
                                        embed=None,
                                        view=None,
                                    )
                                    return
                                g.setdefault("members", []).append(i.user.id)
                                save_data(dl)
                                try:
                                    await self._allow_member_access(i, g, i.user)
                                except Exception:
                                    pass
                                embed_done = discord.Embed(
                                    title="✅ Joined Group",
                                    description=f"You are now part of **{name}**!",
                                    color=0x00FF00,
                                )
                                await i.response.edit_message(
                                    embed=embed_done, view=None
                                )

                            @discord.ui.button(
                                label="Cancel", style=discord.ButtonStyle.secondary
                            )
                            async def cancel(
                                self, i: discord.Interaction, b: discord.ui.Button
                            ):
                                await i.response.edit_message(
                                    content="Join cancelled.", embed=None, view=None
                                )

                        warning = discord.Embed(
                            title="⚠️ Peer Group Agreement",
                            description=(
                                "By joining this peer-led study group, you agree to follow community guidelines and behave respectfully. "
                                "This group is not the official admin-created study space and may be self-managed by students."
                            ),
                            color=0xFFCC00,
                        )
                        await button_inter.response.send_message(
                            embed=warning,
                            view=ConfirmPeerView(button_inter.user.id),
                            ephemeral=True,
                        )
                        return

                    # Admin group: add directly
                    grp.setdefault("members", []).append(button_inter.user.id)
                    save_data(data_local)
                    try:
                        await self._allow_member_access(
                            button_inter, grp, button_inter.user
                        )
                    except Exception:
                        pass
                    await button_inter.response.send_message(
                        f"✅ You joined **{name}**.", ephemeral=True
                    )

            view = GroupView(interaction.user.id)
            await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(
        name="deleteallgroups",
        description="Admin: Delete all study groups and workspace channels",
    )
    @app_commands.default_permissions(administrator=True)
    async def delete_all_groups(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        data = load_data()
        groups = data.get("study_groups", {})
        removed = []
        guild = interaction.guild

        if guild:
            for name, info in list(groups.items()):
                category_id = info.get("workspace_category")
                if category_id:
                    category = guild.get_channel(category_id)
                    if category and isinstance(category, discord.CategoryChannel):
                        try:
                            await category.delete(
                                reason="Cleanup study group workspace"
                            )
                            removed.append(category.name)
                        except Exception:
                            pass
                else:
                    for channel_id in (
                        info.get("workspace_text"),
                        info.get("workspace_voice"),
                    ):
                        ch = guild.get_channel(channel_id) if channel_id else None
                        if ch:
                            try:
                                await ch.delete(reason="Cleanup study group workspace")
                                removed.append(ch.name)
                            except Exception:
                                pass

        data["study_groups"] = {}
        save_data(data)
        await interaction.followup.send(
            f"✅ Deleted all study groups. Removed workspaces: {', '.join(removed) if removed else 'none found.'}",
            ephemeral=True,
        )

    @app_commands.command(
        name="deletegroup",
        description="Admin: Delete one study group and its workspace",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(name="Group name")
    async def delete_group(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        data = load_data()
        group = data.get("study_groups", {}).get(name)
        if not group:
            await interaction.followup.send("❌ Study group not found.", ephemeral=True)
            return

        removed = []
        guild = interaction.guild
        if guild:
            category_id = group.get("workspace_category")
            if category_id:
                category = guild.get_channel(category_id)
                if category and isinstance(category, discord.CategoryChannel):
                    try:
                        await category.delete(
                            reason="Delete single study group workspace"
                        )
                        removed.append(category.name)
                    except Exception:
                        pass
            else:
                for channel_id in (
                    group.get("workspace_text"),
                    group.get("workspace_voice"),
                ):
                    ch = guild.get_channel(channel_id) if channel_id else None
                    if ch:
                        try:
                            await ch.delete(
                                reason="Delete single study group workspace"
                            )
                            removed.append(ch.name)
                        except Exception:
                            pass

        data["study_groups"].pop(name, None)
        save_data(data)
        await interaction.followup.send(
            f"✅ Deleted study group **{name}**. Removed workspaces: {', '.join(removed) if removed else 'none found.'}",
            ephemeral=True,
        )

    @app_commands.command(name="joingroup", description="Join a study group")
    @app_commands.describe(name="Group name")
    async def join_group(self, interaction: discord.Interaction, name: str):
        data = load_data()
        if name not in data["study_groups"]:
            await interaction.response.send_message(
                "❌ Group not found.", ephemeral=True
            )
            return
        group = data["study_groups"][name]

        if interaction.user.id in group["members"]:
            await interaction.response.send_message(
                "You're already in this group.", ephemeral=True
            )
            return

        capacity = group.get("capacity", 20)
        if capacity != 0 and len(group.get("members", [])) >= capacity:
            await interaction.response.send_message(
                "❌ This study group is full.", ephemeral=True
            )
            return

        # If the group is not admin-started, warn the user before joining (peer-led)
        if not group.get("admin_started"):

            class JoinConfirmView(discord.ui.View):
                def __init__(self, author_id: int):
                    super().__init__(timeout=60)
                    self.author_id = author_id

                async def interaction_check(self, inter: discord.Interaction) -> bool:
                    return inter.user.id == self.author_id

                @discord.ui.button(
                    label="Join Anyway", style=discord.ButtonStyle.success
                )
                async def confirm(
                    self, button_inter: discord.Interaction, button: discord.ui.Button
                ):
                    # add member and update message
                    data_local = load_data()
                    grp = data_local["study_groups"].get(name)
                    if grp is None:
                        await button_inter.response.edit_message(
                            content="❌ Group no longer exists.", embed=None, view=None
                        )
                        return
                    if button_inter.user.id in grp["members"]:
                        await button_inter.response.edit_message(
                            content="You're already in this group.",
                            embed=None,
                            view=None,
                        )
                        return
                    capacity = grp.get("capacity", 20)
                    if capacity != 0 and len(grp.get("members", [])) >= capacity:
                        await button_inter.response.edit_message(
                            content="❌ This study group is full.", embed=None, view=None
                        )
                        return
                    grp["members"].append(button_inter.user.id)
                    save_data(data_local)
                    try:
                        await self._allow_member_access(
                            button_inter, grp, button_inter.user
                        )
                    except Exception:
                        pass
                    embed = discord.Embed(
                        title="✅ Joined Group",
                        description=f"You are now part of **{name}**!",
                        color=0x00FF00,
                    )
                    await button_inter.response.edit_message(embed=embed, view=None)

                @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
                async def cancel(
                    self, button_inter: discord.Interaction, button: discord.ui.Button
                ):
                    await button_inter.response.edit_message(
                        content="Join cancelled.", embed=None, view=None
                    )

            warning_embed = discord.Embed(
                title="⚠️ Peer Group Warning",
                description=(
                    "This is a peer-led study group. Note: there is only one admin-started (official) study group. "
                    "Joining this group is voluntary and it may not be monitored by staff. Do you want to continue?"
                ),
                color=0xFFCC00,
            )
            await interaction.response.send_message(
                embed=warning_embed,
                view=JoinConfirmView(interaction.user.id),
                ephemeral=True,
            )
            return

        # Admin-started group — join immediately
        group["members"].append(interaction.user.id)
        save_data(data)
        try:
            await self._allow_member_access(interaction, group, interaction.user)
        except Exception:
            pass

        embed = discord.Embed(
            title="✅ Joined Group",
            description=f"You are now part of **{name}**!",
            color=0x00FF00,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(StudyCog(bot))
