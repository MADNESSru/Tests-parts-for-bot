import os
import logging
import asyncio
import discord
from discord.ext import commands, voice_recv
from dotenv import load_dotenv

import aiohttp
import traceback
import io
import wave

from flask import Flask, request

app = Flask(__name__)

if __name__ == "__main__":
    # Запуск на 0.0.0.0 и порту из переменной окружения PORT (Render требует)
    import os
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

load_dotenv()

# Настройка логгера
logger = logging.getLogger("voice_bot")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
WHISPER_API_KEY = os.getenv("WHISPER_API_KEY")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

class AudioProcessor(voice_recv.AudioSink):
    def __init__(self, user: discord.User, channel: discord.TextChannel, bot: commands.Bot, whisper_api_key: str) -> None:
        super().__init__()
        self.buffer: bytes = b""
        self.target_user: discord.User = user
        self.recording_active: bool = False
        self.channel: discord.TextChannel = channel
        self.bot: commands.Bot = bot
        self.whisper_api_key: str = whisper_api_key
        self.known_ssrcs = set()

    def wants_opus(self) -> bool:
        return False  # Получаем PCM аудио

    def write(self, user, audio_data):
        if hasattr(audio_data, 'ssrc') and audio_data.ssrc not in self.known_ssrcs:
            self.known_ssrcs.add(audio_data.ssrc)
            logger.info(f"Registered new SSRC: {audio_data.ssrc} from user {user}")

        if self.recording_active and audio_data.pcm:
            if user == self.target_user:
                self.buffer += audio_data.pcm

    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_start(self, member: discord.Member) -> None:
        logger.info(f"User {member} started speaking.")
        if member == self.target_user:
            self.recording_active = True

    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_stop(self, member: discord.Member) -> None:
        logger.info(f"User {member.name} stopped speaking.")
        if member == self.target_user:
            self.recording_active = False

            if not self.buffer:
                logger.info("Audio buffer empty, nothing to recognize.")
                return

            try:
                sample_rate = 48000  # Discord PCM sample rate
                sample_width = 2     # 16-bit audio

                with io.BytesIO() as wav_io:
                    with wave.open(wav_io, 'wb') as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(sample_width)
                        wav_file.setframerate(sample_rate)
                        wav_file.writeframes(self.buffer)
                    wav_bytes = wav_io.getvalue()

                self.buffer = b""

                asyncio.run_coroutine_threadsafe(
                    self._send_to_whisper(wav_bytes),
                    self.bot.loop
                )

            except Exception as e:
                logger.error(f"Error processing audio: {e}")
                traceback.print_exc()

    async def _send_to_whisper(self, wav_bytes: bytes):
        logger.info("Sending audio to Whisper API for transcription...")
        url = "https://whisper-api.com/api/v1/async/transcribe"
        headers = {
            "Authorization": f"Bearer {self.whisper_api_key}"
        }
        data = aiohttp.FormData()
        data.add_field("file", wav_bytes, filename="audio.wav", content_type="audio/wav")
        data.add_field("model", "whisper-1")

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    text = result.get("text", "").strip()
                    if text:
                        logger.info(f"Recognized text: {text}")
                        await self.channel.send(f"Распознанный текст: {text}")
                    else:
                        logger.info("Whisper API returned empty text.")
                else:
                    error_text = await resp.text()
                    logger.error(f"Recognition error: HTTP {resp.status} - {error_text}")
                    await self.channel.send(f"Ошибка распознавания: HTTP {resp.status}")

    def cleanup(self) -> None:
        logger.info("AudioSink cleanup complete.")

# Команда для захода в голосовой канал
@bot.command()
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        if ctx.voice_client is not None:
            await ctx.voice_client.move_to(channel)
            logger.info(f"Moved to channel: {channel.name}")
        else:
            await channel.connect()
            logger.info(f"Connected to channel: {channel.name}")
        await ctx.send(f"Подключился к {channel.name}")
    else:
        await ctx.send("Вы не в голосовом канале!")
        logger.warning("User not in voice channel.")

# Команда для выхода из голосового канала
@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        logger.info("Disconnected from voice channel.")
        await ctx.send("Отключился от голосового канала.")
    else:
        await ctx.send("Я не в голосовом канале.")
        logger.warning("Bot not in voice channel.")

# Команда для запуска прослушки пользователя в голосовом канале
@bot.command()
async def listen(ctx, user: discord.Member):
    voice_client = ctx.voice_client
    if not voice_client or not voice_client.is_connected():
        await ctx.send("Я должен быть в голосовом канале, чтобы слушать.")
        logger.warning("Bot not connected to voice channel.")
        return

    # Останавливаем предыдущий sink, если был
    if hasattr(voice_client, "stop_recording"):
        voice_client.stop_recording()

    audio_processor = AudioProcessor(user=user, channel=ctx.channel, bot=bot, whisper_api_key=WHISPER_API_KEY)
    voice_client.start_recording(audio_processor, finished_callback=lambda sink, *args: logger.info("Recording finished."), ctx)
    await ctx.send(f"Начал слушать речь пользователя {user.display_name}.")

bot.run(TOKEN)
