from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from utils import load_data, save_data


class PlannerCog(commands.Cog, name="Planner"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="addtask", description="Add a new task")
    @app_commands.describe(task="Task description")
    async def add_task(self, interaction: discord.Interaction, task: str):
        data = load_data()
        user_id = str(interaction.user.id)

        if user_id not in data["tasks"]:
            data["tasks"][user_id] = []

        task_id = len(data["tasks"][user_id]) + 1
        data["tasks"][user_id].append(
            {
                "id": task_id,
                "task": task,
                "done": False,
                "created": datetime.now().isoformat(),
            }
        )
        save_data(data)

        embed = discord.Embed(title="✅ Task Added", description=task, color=0x00FF88)
        embed.add_field(name="Task ID", value=f"**#{task_id}**", inline=True)
        embed.set_footer(text=f"Added by {interaction.user}")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="mytasks", description="Show your tasks")
    async def my_tasks(self, interaction: discord.Interaction):
        data = load_data()
        tasks = data["tasks"].get(str(interaction.user.id), [])

        if not tasks:
            await interaction.response.send_message("You have no tasks yet.")
            return

        embed = discord.Embed(title="📋 Your Tasks", color=0xFFAA00)

        for t in tasks:
            status = "✅" if t["done"] else "⬜"
            embed.add_field(name=f"{status} #{t['id']}", value=t["task"], inline=False)

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(PlannerCog(bot))
