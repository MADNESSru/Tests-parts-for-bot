import os
import discord
from discord.ext import commands
import logging
import aiohttp
import asyncio
from dotenv import load_dotenv
import os
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Render Web Service is running"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)


# Загружаем переменные окружения из файла .env
load_dotenv()

# Получаем токены из переменных окружения
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
WHISPER_API_KEY = os.getenv("WHISPER_API_KEY")

# Настройка логгера
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

@bot.command()
async def listen(ctx, duration: int = 10):
    voice_client = ctx.voice_client
    if not voice_client:
        logger.warning("Бот не в голосовом канале.")
        return

    logger.info(f"Начинаю запись аудио в течение {duration} секунд...")
    audio_sink = discord.sinks.WaveSink()
    voice_client.start_recording(
        audio_sink,
        finished_callback=lambda sink, *args: asyncio.create_task(process_audio(sink, ctx)),
        ctx
    )
    await asyncio.sleep(duration)
    voice_client.stop_recording()
    logger.info("Запись завершена.")

async def process_audio(sink, ctx):
    for user_id, audio in sink.audio_data.items():
        filename = f"audio_{user_id}.wav"
        with open(filename, "wb") as f:
            f.write(audio.file.read())

        logger.info(f"Аудио пользователя {user_id} сохранено как {filename}. Отправляю в Whisper API...")

        async with aiohttp.ClientSession() as session:
            with open(filename, "rb") as audio_file:
                headers = {"Authorization": f"Bearer {WHISPER_API_KEY}"}
                data = aiohttp.FormData()
                data.add_field("file", audio_file, filename=filename, content_type="audio/wav")
                async with session.post("https://api.openai.com/v1/audio/transcriptions", headers=headers, data=data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        text = result.get("text", "")
                        logger.info(f"Распознанный текст: {text}")
                    else:
                        logger.error(f"Ошибка при распознавании: {resp.status}")

bot.run(TOKEN)
