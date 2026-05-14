from __future__ import annotations

import os
import re
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
TITLE_TRIGGER_FIRST = int(os.getenv("TITLE_TRIGGER_FIRST", "2"))
TITLE_TRIGGER_INTERVAL = int(os.getenv("TITLE_TRIGGER_INTERVAL", "10"))

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.5-flash")

# thread_id -> 봇 메시지 제외 누적 카운트
thread_message_counts: dict[int, int] = {}
# 카운트 초기화 진행 중인 thread_id 집합 (race condition 방지)
_initializing: set[int] = set()
# 제목 갱신 진행 중인 (thread_id, count) 집합 (중복 트리거 방어)
_updating: set[tuple[int, int]] = set()

TITLE_PROMPT = """\
아래는 Discord 스레드의 최근 대화 내용입니다.
이 대화의 핵심 주제를 반영하는 제목을 한국어(영어 혼용 가능)로 20자 이내로 작성하세요.
제목만 출력하고 따옴표, 설명, 줄바꿈은 포함하지 마세요.

대화:
{messages}
"""

MAX_MESSAGES_FOR_CONTEXT = 20

# 툴 사용 메시지 패턴: "💻 terminal: "..." 형태 제외
TOOL_USE_PATTERN = re.compile(r'^\S+\s+[\w_-]+:\s+"')


def is_tool_use_message(content: str) -> bool:
    return bool(TOOL_USE_PATTERN.match(content))


def should_update_title(count: int) -> bool:
    return count == TITLE_TRIGGER_FIRST or (count > TITLE_TRIGGER_FIRST and (count - TITLE_TRIGGER_FIRST) % TITLE_TRIGGER_INTERVAL == 0)


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
        response = await gemini_model.generate_content_async(prompt)
        title = response.text.strip().strip('"\'').rstrip('.。')

        if len(title) > 100:
            title = title[:100]

        return title
    except Exception as e:
        logger.error("Gemini API 호출 실패 (thread_id=%d): %s", thread.id, e)
        return None


async def update_thread_title(thread: discord.Thread, count: int) -> None:
    key = (thread.id, count)
    if key in _updating:
        return
    _updating.add(key)
    try:
        title = await generate_title(thread)
        if not title:
            return
        await thread.edit(name=title, reason=f"AI auto-rename (msg #{count})")
        logger.info("제목 갱신 완료 (thread_id=%d): %s", thread.id, title)
    except discord.Forbidden:
        logger.warning("스레드 제목 수정 권한 없음 (thread_id=%d)", thread.id)
    except discord.HTTPException as e:
        logger.error("Discord API 오류 (thread_id=%d): %s", thread.id, e)
    finally:
        _updating.discard(key)


intents = discord.Intents.default()
intents.message_content = True
intents.guild_messages = True

client = discord.Client(intents=intents)


async def initialize_thread_count(thread: discord.Thread) -> int:
    """해당 스레드의 실제 메시지 수를 Discord API로 조회해서 카운트 초기화."""
    count = 0
    try:
        async for msg in thread.history(limit=None, oldest_first=True):
            if msg.author.bot:
                continue
            if is_tool_use_message(msg.content):
                continue
            count += 1
        thread_message_counts[thread.id] = count
        logger.info(
            "카운트 초기화 (thread_id=%d, name=%r, count=%d)",
            thread.id, thread.name, count,
        )
    except (discord.Forbidden, discord.HTTPException) as e:
        logger.warning("카운트 초기화 실패 (thread_id=%d): %s", thread.id, e)
        thread_message_counts[thread.id] = 0
    return thread_message_counts[thread.id]


@client.event
async def on_ready():
    logger.info("봇 준비 완료: %s (id=%d)", client.user, client.user.id)


@client.event
async def on_message(message: discord.Message):
    # 모든 메시지 수신 확인용 (디버그)
    logger.debug("메시지 수신: channel=%s type=%s author=%s content=%s",
                message.channel, type(message.channel).__name__, message.author, message.content[:50])

    if not isinstance(message.channel, discord.Thread):
        return

    # 봇 메시지 카운팅 제외
    if message.author.bot:
        return

    # 툴 사용 메시지 (💻 terminal: "..." 등) 카운팅 제외
    if is_tool_use_message(message.content):
        return

    thread_id = message.channel.id

    # 처음 보는 스레드면 실제 히스토리로 카운트 초기화
    if thread_id not in thread_message_counts and thread_id not in _initializing:
        _initializing.add(thread_id)
        try:
            await initialize_thread_count(message.channel)
        finally:
            _initializing.discard(thread_id)
    elif thread_id in _initializing:
        # 초기화 중에 들어온 메시지는 스킵 (history fetch에 이미 포함됨)
        return

    thread_message_counts[thread_id] = thread_message_counts.get(thread_id, 0) + 1
    count = thread_message_counts[thread_id]

    logger.info(
        "스레드 메시지 수신 (thread_id=%d, count=%d, author=%s)",
        thread_id, count, message.author,
    )

    if should_update_title(count):
        logger.info(
            "제목 갱신 트리거 (thread_id=%d, count=%d)", thread_id, count
        )
        await update_thread_title(message.channel, count)


if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN 환경변수가 설정되지 않았습니다.")
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")

    client.run(DISCORD_BOT_TOKEN, log_handler=None)
