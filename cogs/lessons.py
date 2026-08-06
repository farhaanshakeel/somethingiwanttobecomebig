import io
from datetime import datetime, timezone
import textwrap

import discord
from discord import app_commands
from discord.ext import commands

from utils import load_data, save_data

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except Exception:
    MATPLOTLIB_AVAILABLE = False


class LessonsCog(commands.Cog, name="Lessons"):
    def __init__(self, bot):
        self.bot = bot

    def _record_lesson(
        self,
        interaction: discord.Interaction,
        title: str,
        content: str,
        latex: bool,
    ):
        data = load_data()
        lessons = data.setdefault("lessons", [])
        lessons.append(
            {
                "id": len(lessons) + 1,
                "title": title,
                "content": content,
                "latex": latex,
                "created": datetime.now(timezone.utc).isoformat(),
                "author_id": interaction.user.id,
                "author_name": str(interaction.user),
                "guild_id": interaction.guild.id if interaction.guild else None,
                "channel_id": interaction.channel.id if interaction.channel else None,
            }
        )
        save_data(data)

    @app_commands.command(
        name="lesson",
        description="Admin-only: Send a lesson; renders LaTeX if requested",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        title="Lesson title",
        content="Lesson text or LaTeX",
        latex="Render content as LaTeX image?",
    )
    async def send_lesson(
        self,
        interaction: discord.Interaction,
        title: str,
        content: str,
        latex: bool = False,
    ):
        await interaction.response.defer()
        self._record_lesson(interaction, title, content, latex)

        if latex and MATPLOTLIB_AVAILABLE:
            # Render LaTeX to PNG using matplotlib's mathtext
            try:
                wrapped = textwrap.fill(content, width=200)
                fig = plt.figure(figsize=(8, 0.5 + len(wrapped) / 80))
                fig.patch.set_alpha(0.0)
                plt.axis("off")
                plt.text(
                    0.5,
                    0.5,
                    f"${content}$",
                    horizontalalignment="center",
                    verticalalignment="center",
                    fontsize=16,
                )

                buf = io.BytesIO()
                plt.savefig(
                    buf, format="png", bbox_inches="tight", dpi=200, transparent=True
                )
                plt.close(fig)
                buf.seek(0)

                file = discord.File(fp=buf, filename="lesson.png")
                embed = discord.Embed(title=title, color=0xFF6600)
                embed.set_image(url="attachment://lesson.png")
                await interaction.followup.send(embed=embed, file=file)
                return
            except Exception:
                # Fallthrough to plain text on render failure
                pass

        # Non-latex or fallback: send as embed with code block for readability
        display = content if len(content) <= 1900 else content[:1897] + "..."
        embed = discord.Embed(
            title=title, description=f"```\n{display}\n```", color=0xFF6600
        )
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(LessonsCog(bot))
