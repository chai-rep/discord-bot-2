import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone, timedelta
from config import ROLE_ORDER, TARGET_GUILD_ID, LOG_CHANNEL_ID, LOGBOOK_CHANNELS
import asyncio

# Korea Standard Time
KST = timezone(timedelta(hours=9))


class DailyRoleAssigner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_task.start()

    def cog_unload(self):
        self.daily_task.cancel()

    @tasks.loop(minutes=60)
    async def daily_task(self):
        """Runs once daily at 09:00 KST"""
        now_kst = datetime.now(KST)
        if now_kst.hour != 9:
            return
        print("⏰ Running daily role log task...")
        await self.assign_roles()

    async def assign_roles(self, interaction: discord.Interaction = None):
        """Scan logbook channels and assign roles"""
        guild = self.bot.get_guild(TARGET_GUILD_ID)
        if not guild:
            print("⚠️ Target guild not found.")
            if interaction:
                await interaction.response.send_message("⚠️ Target guild not found.", ephemeral=True)
            return

        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if not log_channel:
            print("⚠️ Log channel not found.")
            if interaction:
                await interaction.response.send_message("⚠️ Log channel not found.", ephemeral=True)
            return

        all_mentions = []  # List of (msg, user_id) tuples
        print("📚 Scanning logbook channels for mentions...")

        for channel_id in LOGBOOK_CHANNELS:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                print(f"⚠️ Could not access channel {channel_id}")
                continue

            try:
                # Scan messages from newest to oldest
                async for msg in channel.history(limit=None, oldest_first=False):
                    # Stop scanning older messages if a 👍 reaction is found
                    if any(reaction.emoji == "👍" for reaction in msg.reactions):
                        print(f"🛑 Stopped scanning {channel.name} at message {msg.id} (found 👍)")
                        break

                    for user in msg.mentions:
                        all_mentions.append((msg, user.id))
            except discord.Forbidden:
                print(f"⚠️ Missing permission to read {channel.name}")
            except Exception as e:
                print(f"❌ Error scanning {channel.id}: {e}")

        print(f"📘 Found {len(all_mentions)} mentions to evaluate.")

        logged_users = []
        removed_rollcall_users = []

        # ✅ Count how many times each user was mentioned
        mention_counts = {}
        for msg, user_id in all_mentions:
            mention_counts[user_id] = mention_counts.get(user_id, 0) + 1

        # ✅ Process each user based on how many times they were mentioned
        for user_id, count in mention_counts.items():
            try:
                member = await guild.fetch_member(user_id)
            except Exception as e:
                print(f"❌ Could not fetch member {user_id}: {e}")
                continue

            role1 = guild.get_role(ROLE_ORDER[0])
            role2 = guild.get_role(ROLE_ORDER[1])
            role3 = guild.get_role(ROLE_ORDER[2])
            roll_call = guild.get_role(ROLE_ORDER[3])

            # Promote one step per mention (so multiple mentions = multiple promotions)
            for _ in range(count):
                next_role = None
                if roll_call in member.roles and role1 not in member.roles:
                    next_role = role1
                elif role1 in member.roles and role2 not in member.roles:
                    next_role = role2
                elif role2 in member.roles and role3 not in member.roles:
                    next_role = role3

                if not next_role:
                    break

                try:
                    await member.add_roles(next_role, reason="Logbook")
                    logged_users.append((member, next_role))
                    print(f"✅ Assigned {next_role.name} to {member.display_name}")
                    await asyncio.sleep(0.25)

                    if next_role == role3 and roll_call in member.roles:
                        await member.remove_roles(roll_call, reason="Reached Role 3")
                        removed_rollcall_users.append(member)
                        print(f"❌ Removed Roll Call from {member.display_name}")
                        break  # Stop further promotions after reaching role 3
                except discord.Forbidden:
                    print(f"⚠️ Missing permission for {member.display_name}")
                except Exception as e:
                    print(f"❌ Error assigning role to {member.display_name}: {e}")

        # ✅ React to all processed messages
        for msg, _ in all_mentions:
            try:
                await msg.add_reaction("👍")
            except Exception:
                pass

        # ✅ Send grouped summary embed
        if logged_users:
            role1_users = [m.mention for m, r in logged_users if r.id == ROLE_ORDER[0]]
            role2_users = [m.mention for m, r in logged_users if r.id == ROLE_ORDER[1]]
            role3_users = [m.mention for m, r in logged_users if r.id == ROLE_ORDER[2]]

            embed = discord.Embed(
                title="Daily Role Log Summary",
                description=f"{len(logged_users)} total roles assigned across logbooks.",
                color=0x57F287,
                timestamp=datetime.now(KST),
            )

            if role1_users:
                embed.add_field(name="Role 1:", value=" ".join(role1_users), inline=False)
            if role2_users:
                embed.add_field(name="Role 2:", value=" ".join(role2_users), inline=False)
            if role3_users:
                embed.add_field(name="Role 3:", value=" ".join(role3_users), inline=False)
            if removed_rollcall_users:
                embed.add_field(
                    name="Roll Call Removed:",
                    value=" ".join(m.mention for m in removed_rollcall_users),
                    inline=False,
                )

            embed.set_footer(text="Automated Logbook Bot")
            await log_channel.send(embed=embed)
        else:
            await log_channel.send(
                f"✅ Daily check complete — no roles assigned. ({datetime.now(KST).strftime('%Y-%m-%d')})"
            )

        if interaction:
            await interaction.response.send_message("✅ Role log completed manually.", ephemeral=True)

    @daily_task.before_loop
    async def before_daily_task(self):
        await self.bot.wait_until_ready()
        print("✅ DailyRoleAssigner loaded and waiting for 09:00 KST run.")

    @app_commands.command(name="log_roles", description="Manually run the daily role log")
    async def log_roles_command(self, interaction: discord.Interaction):
        await self.assign_roles(interaction=interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(DailyRoleAssigner(bot))
