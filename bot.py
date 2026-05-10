import os
import logging
import discord
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.0-flash-lite")

# thread_id -> 봇 메시지 제외 누적 카운트
thread_message_counts: dict[int, int] = {}

TITLE_PROMPT = """\
아래는 Discord 스레드의 최근 대화 내용입니다.
이 대화의 핵심 주제를 반영하는 제목을 한국어(영어 혼용 가능)로 20자 이내로 작성하세요.
제목만 출력하고 따옴표, 설명, 줄바꿈은 포함하지 마세요.

대화:
{messages}
"""

MAX_MESSAGES_FOR_CONTEXT = 20


def should_update_title(count: int) -> bool:
    return count == 2 or (count > 2 and (count - 2) % 10 == 0)


async def fetch_recent_messages(thread: discord.Thread) -> list[discord.Message]:
    messages = []
    async for msg in thread.history(limit=MAX_MESSAGES_FOR_CONTEXT, oldest_first=True):
        messages.append(msg)
    return messages


def format_messages_for_prompt(messages: list[discord.Message]) -> str:
    lines = []
    for msg in messages:
        author = msg.author.display_name
        content = msg.content.strip()
        if content:
            lines.append(f"{author}: {content}")
    return "\n".join(lines)


async def generate_title(thread: discord.Thread) -> str | None:
    try:
        messages = await fetch_recent_messages(thread)
        formatted = format_messages_for_prompt(messages)
        if not formatted:
            return None

        prompt = TITLE_PROMPT.format(messages=formatted)
        response = gemini_model.generate_content(prompt)
        title = response.text.strip()

        if len(title) > 100:
            title = title[:100]

        return title
    except Exception as e:
        logger.error("Gemini API 호출 실패 (thread_id=%d): %s", thread.id, e)
        return None


async def update_thread_title(thread: discord.Thread) -> None:
    title = await generate_title(thread)
    if not title:
        return

    try:
        await thread.edit(name=title)
        logger.info("제목 갱신 완료 (thread_id=%d): %s", thread.id, title)
    except discord.Forbidden:
        logger.warning("스레드 제목 수정 권한 없음 (thread_id=%d)", thread.id)
    except discord.HTTPException as e:
        logger.error("Discord API 오류 (thread_id=%d): %s", thread.id, e)


intents = discord.Intents.default()
intents.message_content = True
intents.guild_messages = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    logger.info("봇 준비 완료: %s (id=%d)", client.user, client.user.id)


@client.event
async def on_message(message: discord.Message):
    if not isinstance(message.channel, discord.Thread):
        return

    if message.author.bot:
        return

    thread_id = message.channel.id
    thread_message_counts[thread_id] = thread_message_counts.get(thread_id, 0) + 1
    count = thread_message_counts[thread_id]

    logger.debug(
        "스레드 메시지 수신 (thread_id=%d, count=%d, author=%s)",
        thread_id, count, message.author,
    )

    if should_update_title(count):
        logger.info(
            "제목 갱신 트리거 (thread_id=%d, count=%d)", thread_id, count
        )
        await update_thread_title(message.channel)


if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN 환경변수가 설정되지 않았습니다.")
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")

    client.run(DISCORD_BOT_TOKEN, log_handler=None)
