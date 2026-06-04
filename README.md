# 다카이브봇

다카이브봇은 관심 있는 글, 메모, 캡처, 사진, 문서를 Telegram 채팅방에 올리면 로컬에 저장하고, 이후 scheduled processor가 Codex를 중간 처리자로 사용해 SQLite에 정리하는 개인 아카이브 봇입니다.

MVP 목표는 활용 기능을 넓히는 것이 아니라 안정적인 수집과 정리 파이프라인을 만드는 것입니다. 일정, 일지, 태그 기반 요약, Telegram 정리 출력은 후속 단계로 둡니다.

## 빠른 시작

```bash
cd /Users/hennei/workspace/darchivebot
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
darchive init
darchive doctor
```

`.env`에 Telegram token과 허용 채팅방을 넣습니다.

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_IDS=
TELEGRAM_ADMIN_USER_IDS=
DARCHIVE_ALLOW_ALL_CHATS=false
```

## 명령어

```bash
darchive init
darchive setup
darchive doctor
darchive doctor --online
darchive discover-chat
darchive rooms
darchive telegram-commands show
darchive telegram-commands sync
darchive telegram
darchive pending
darchive process
darchive process --no-codex
darchive list
darchive show <capture-id>
darchive send-test --chat-id <telegram-chat-id>
```

- `telegram`: Telegram polling으로 텍스트, 캡션, 사진, 문서를 캡처하고 media 파일을 `.local/captures/`에 저장합니다.
- `pending`: processor가 처리할 pending capture와 Codex/image 입력 계획을 미리 봅니다.
- `process`: pending capture를 Codex CLI non-interactive mode로 보내 구조화된 archive metadata를 받고 SQLite에 저장합니다.
- `process --no-codex`: Codex 없이 텍스트/캡션과 optional OCR fallback만 사용합니다. 로컬 점검과 테스트용입니다.

## Codex processor

`darchive process`는 기본적으로 `codex exec`를 사용합니다.

- Codex는 capture packet과 이미지 파일을 읽습니다.
- Codex 결과는 JSON Schema로 제한됩니다.
- Python 코드가 결과를 검증한 뒤 SQLite에 씁니다.
- Codex 실행이 실패하면 capture는 `failed_retryable` 상태로 남아 재시도할 수 있습니다.

주요 설정:

```env
DARCHIVE_CODEX_ENABLED=true
DARCHIVE_CODEX_BIN=codex
DARCHIVE_CODEX_MODEL=
DARCHIVE_CODEX_SANDBOX=read-only
DARCHIVE_CODEX_EPHEMERAL=true
DARCHIVE_CODEX_TIMEOUT_SEC=900
```

## macOS launchd

```bash
scripts/install_launch_agent.sh
scripts/uninstall_launch_agent.sh
```

설치 스크립트는 두 개의 LaunchAgent를 만듭니다.

- `com.hennei.darchivebot.telegram`: Telegram polling bot을 계속 실행합니다.
- `com.hennei.darchivebot.processor`: 5분마다 `darchive process`를 실행합니다.

## 보안

`.env`, `.local/`, SQLite DB, 로그, 캡처 파일은 커밋하지 않습니다. Codex는 DB를 직접 수정하지 않고 구조화된 JSON만 반환합니다.

공개 전 점검:

```bash
scripts/preflight_public.sh
pytest
```
