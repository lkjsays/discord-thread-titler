# Discord Thread Auto-Titler — Claude 컨텍스트

## 프로젝트 요약

Discord 서버의 스레드에서 메시지를 감지해 Gemini Flash API로 제목을 자동 갱신하는 단일 파일 봇.

## 핵심 파일

| 파일 | 역할 |
|------|------|
| `bot.py` | 메인 봇 코드 (전체 로직) |
| `requirements.txt` | Python 의존성 |
| `.env` | 실제 환경변수 (gitignore됨) |
| `.env.example` | 환경변수 템플릿 |
| `launchd/com.kjlee.discord-thread-titler.plist` | macOS 자동 실행 설정 |

## 제목 갱신 트리거 로직

`should_update_title(count)` 함수:
- `count == 2` → 첫 갱신
- `count > 2 and (count - 2) % 10 == 0` → 이후 10개마다 (12, 22, 32, …)
- 봇 메시지는 카운트에서 제외

## 환경변수

- `DISCORD_BOT_TOKEN` — Discord Bot 토큰
- `GEMINI_API_KEY` — Google Gemini API 키

## Gemini 사용

- 모델: `gemini-2.0-flash-lite`
- 최근 20개 메시지 컨텍스트
- 한국어/영어 혼용, 20자 이내 제목

## Discord Intents

```python
intents.message_content = True  # Privileged — 포털에서 수동 활성화 필요
intents.guild_messages = True
```

## 에러 처리 방침

- Gemini 실패 → 로그 후 제목 유지 (조용히 실패)
- Discord API 실패 → 로그 후 계속 실행
- 재시작 시 카운트 리셋 허용 (단순성 우선)
