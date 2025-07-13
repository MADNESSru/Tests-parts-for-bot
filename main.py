import os
import discord
from discord.ext import commands
import logging
import aiohttp
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
WHISPER_API_KEY = os.getenv("WHISPER_API_KEY")

logger = logging.getLogger("voice_bot")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command()
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        logger.info(f"Бот подключился к голосовому каналу: {channel.name}")
    else:
        logger.warning("Пользователь не в голосовом канале.")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        logger.info("Бот отключился от голосового канала.")
    else:
        logger.warning("Бот не в голосовом канале.")

# Пример команды, которая просто сообщает, что слушает (реализация записи аудио требует сложной настройки)
@bot.command()
async def listen(ctx):
    if not ctx.voice_client:
        logger.warning("Бот не в голосовом канале.")
        return
    logger.info("Команда listen вызвана, но запись аудио требует дополнительной реализации.")
    await ctx.send("Функция записи аудио пока не реализована в этом примере.")

bot.run(TOKEN)
