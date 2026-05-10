# Discord Thread Auto-Titler

Discord 스레드에 메시지가 쌓이면 Gemini Flash API로 대화를 분석해 제목을 자동 갱신하는 봇.

## 동작 방식

- 스레드에 사용자 메시지가 **2개** 쌓이면 첫 제목 생성
- 이후 **10개마다** (12, 22, 32, …) 제목 재갱신
- 봇 자신의 메시지는 카운트에서 제외
- Gemini `gemini-2.0-flash-lite` 모델로 한국어 20자 이내 제목 생성

## 설정

### 1. 환경변수

```bash
cp .env.example .env
# .env 파일에 실제 토큰 값 입력
```

| 변수 | 설명 |
|------|------|
| `DISCORD_BOT_TOKEN` | Discord Developer Portal에서 발급 |
| `GEMINI_API_KEY` | Google AI Studio에서 발급 |

### 2. Discord Bot 설정

[Discord Developer Portal](https://discord.com/developers/applications)에서:

**Privileged Gateway Intents** (Bot → Privileged Gateway Intents):
- `MESSAGE CONTENT INTENT` — **필수** (활성화 필요)
- `SERVER MEMBERS INTENT` — 불필요
- `PRESENCE INTENT` — 불필요

**Bot Permissions**:
- `Read Messages / View Channels`
- `Send Messages`
- `Manage Threads`

**OAuth2 URL 생성** (OAuth2 → URL Generator):
- Scopes: `bot`
- Bot Permissions: 위 항목 체크
- 생성된 URL로 서버에 봇 초대

### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

### 4. 실행

```bash
python bot.py
```

## macOS launchd로 자동 실행

로그 디렉토리 생성 후 서비스 등록:

```bash
mkdir -p logs
cp launchd/com.kjlee.discord-thread-titler.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.kjlee.discord-thread-titler.plist
```

서비스 상태 확인:

```bash
launchctl list | grep discord-thread-titler
tail -f logs/bot.log
```

서비스 중지:

```bash
launchctl unload ~/Library/LaunchAgents/com.kjlee.discord-thread-titler.plist
```

## 주의사항

- 봇 재시작 시 스레드별 메시지 카운트가 초기화됩니다 (의도적 설계).
- Gemini API 호출 실패 시 제목 변경 없이 로그만 기록하고 계속 실행됩니다.
- `Manage Threads` 권한이 없으면 제목 변경에 실패합니다.
