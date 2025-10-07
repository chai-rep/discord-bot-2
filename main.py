import discord
from discord.ext import commands
import boto3
import asyncio
import config

# ---------------- Discord Setup ----------------
intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)



# ---------------- Event Listener ----------------
@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}!")
    try:
        synced = await bot.tree.sync()
        print(f"Slash commands synced: {len(synced)}")
    except Exception as e:
        print("Error syncing commands:", e)

# ---------------- Main Async ----------------
async def main():
    async with bot:
        # Load cogs here
        await bot.load_extension("cogs.dailyrole")
      

        # Start bot
        await bot.start(config.DISCORD_TOKEN)

# ---------------- Run Bot ----------------
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped manually")
    except Exception as e:
        print("Bot encountered an error:", e)