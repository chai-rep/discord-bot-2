import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone, timedelta
from config import ROLE_ORDER, TARGET_GUILD_ID, LOG_CHANNEL_ID, LOGBOOK_CHANNELS
import asyncio
import re  

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
        print("Running daily role log task...")
        await self.assign_roles()

    async def assign_roles(self, interaction: discord.Interaction = None):
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

        all_mentions = []  # List of (msg, user_id)
        print("Scanning logbook channels for mentions...")

        for channel_id in LOGBOOK_CHANNELS:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                print(f"⚠️ Could not access channel {channel_id}")
                continue

            try:
                async for msg in channel.history(limit=None, oldest_first=False):
                    if any(reaction.emoji == "👍" for reaction in msg.reactions):
                        print(f"🛑 Stopped scanning {channel.name} at message {msg.id} (found 👍)")
                        break

                    mention_tokens = re.findall(r"<@!?\d+>", msg.content or "")
                    if mention_tokens:
                        for token in mention_tokens:
                            user_id = int(re.search(r"\d+", token).group())
                            all_mentions.append((msg, user_id))
                    else:
                        for user in msg.mentions:
                            all_mentions.append((msg, user.id))

            except discord.Forbidden:
                print(f"⚠️ Missing permission to read {channel.name}")
            except Exception as e:
                print(f"❌ Error scanning {channel.id}: {e}")

        print(f"📘 Found {len(all_mentions)} mentions to evaluate.\n")

        logged_users = []
        removed_rollcall_users = []

        for msg, user_id in all_mentions:
            print(f"Processing mention: user_id={user_id} message_id={msg.id}")
            try:
                member = await guild.fetch_member(user_id)
            except Exception as e:
                print(f"❌ Could not fetch member {user_id}: {e}")
                continue

            role1 = guild.get_role(ROLE_ORDER[0])
            role2 = guild.get_role(ROLE_ORDER[1])
            role3 = guild.get_role(ROLE_ORDER[2])
            roll_call = guild.get_role(ROLE_ORDER[3])

            next_role = None
            if roll_call in member.roles and role1 not in member.roles:
                next_role = role1
            elif role1 in member.roles and role2 not in member.roles:
                next_role = role2
            elif role2 in member.roles and role3 not in member.roles:
                next_role = role3

            if next_role:
                try:
                    await member.add_roles(next_role, reason="Logbook")
                    logged_users.append((member, next_role))
                    print(f"✅ Assigned {next_role.name} to {member.display_name}")
                    await asyncio.sleep(0.25)

                    if next_role == role3 and roll_call in member.roles:
                        try:
                            await member.remove_roles(roll_call, reason="Reached Role 3")
                            removed_rollcall_users.append(member)
                        except Exception as e:
                            print(f"⚠️ Could not remove Roll Call from {member.display_name}: {e}")

                except discord.Forbidden:
                    print(f"⚠️ Missing permission for {member.display_name}")
                except Exception as e:
                    print(f"❌ Error assigning role to {member.display_name}: {e}")

            try:
                await msg.add_reaction("👍")
            except Exception as e:
                print(f"❌ Could not react to message {msg.id}: {e}")

        print(f"\n📊 Summary: {len(logged_users)} roles assigned.\n")

        # ✅ Split embed safely
        if logged_users:
            role1_users = [m.mention for m, r in logged_users if r.id == ROLE_ORDER[0]]
            role2_users = [m.mention for m, r in logged_users if r.id == ROLE_ORDER[1]]
            role3_users = [m.mention for m, r in logged_users if r.id == ROLE_ORDER[2]]
            removed_users = [m.mention for m in removed_rollcall_users]

            all_sections = []

            if role1_users:
                all_sections.append(("Role 1:", role1_users))
            if role2_users:
                all_sections.append(("Role 2:", role2_users))
            if role3_users:
                all_sections.append(("Role 3:", role3_users))
            if removed_users:
                all_sections.append(("Roll Call Removed:", removed_users))

            def chunk_mentions(mentions, limit=1000):
                """Split mentions list so each chunk fits safely."""
                chunks = []
                current = []
                current_len = 0
                for mention in mentions:
                    if current_len + len(mention) + 1 > limit:
                        chunks.append(" ".join(current))
                        current = [mention]
                        current_len = len(mention)
                    else:
                        current.append(mention)
                        current_len += len(mention) + 1
                if current:
                    chunks.append(" ".join(current))
                return chunks

            embeds_to_send = []

            for name, mentions in all_sections:
                chunks = chunk_mentions(mentions, limit=1000)
                for i, chunk in enumerate(chunks, start=1):
                    embeds_to_send.append((f"{name} (Part {i})" if len(chunks) > 1 else name, chunk))

            # Build embeds in 6000-character groups
            current_embed = discord.Embed(
                title="Daily Role Log Summary",
                description=f"{len(logged_users)} total roles assigned across logbooks.",
                color=0x57F287,
                timestamp=datetime.now(KST),
            )
            current_len = 0

            for name, value in embeds_to_send:
                if current_len + len(value) > 5500 or len(current_embed.fields) >= 25:
                    await log_channel.send(embed=current_embed)
                    current_embed = discord.Embed(
                        title="Daily Role Log Summary (cont.)",
                        color=0x57F287,
                        timestamp=datetime.now(KST),
                    )
                    current_len = 0
                current_embed.add_field(name=name, value=value, inline=False)
                current_len += len(value)
            
            if len(current_embed.fields) > 0:
                current_embed.set_footer(text="Automated Logbook Bot")
                await log_channel.send(embed=current_embed)

        else:
            await log_channel.send(
                f"✅ Daily check complete — no roles assigned. ({datetime.now(KST).strftime('%Y-%m-%d')})"
            )

        if interaction:
            await interaction.response.send_message("✅ Role log completed manually.", ephemeral=True)

    @daily_task.before_loop
    async def before_daily_task(self):
        await self.bot.wait_until_ready()
        print("✅ bot waiting for 09:00 KST run.")

    @app_commands.command(
        name="log_roles", description="Manually run the daily role log"
    )
    async def log_roles_command(self, interaction: discord.Interaction):
        await self.assign_roles(interaction=interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(DailyRoleAssigner(bot))
