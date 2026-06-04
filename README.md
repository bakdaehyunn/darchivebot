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

개인 아카이브 용도는 Telegram 그룹보다 봇과의 1:1 채팅을 권장합니다. 그룹을 쓰면 BotFather의 Group Privacy 때문에 일반 메시지나 사진이 캡처되지 않을 수 있습니다.

`.env`에 Telegram token과 허용 채팅방을 넣습니다. token, chat id, admin user id는 출력하거나 커밋하지 않습니다.

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_IDS=
TELEGRAM_ADMIN_USER_IDS=
DARCHIVE_ALLOW_ALL_CHATS=false
```

테스트된 설정 흐름:

```bash
darchive setup --non-interactive \
  --telegram-bot-token '<BOT_TOKEN>' \
  --telegram-chat-id '<CHAT_ID>' \
  --telegram-admin-user-id '<YOUR_USER_ID>'
darchive doctor --online
darchive telegram-commands sync
darchive send-test --allowed
```

일반 운영은 launchd/cron이 poller와 processor를 관리하는 방식입니다.

```bash
scripts/install_launch_agent.sh
```

직접 실행하는 명령은 테스트/디버그용입니다. 캡처 동작을 확인할 때만 한 터미널에서 capture poller를 켜 둡니다.

```bash
darchive telegram
```

다른 터미널에서 처리 계획과 상태를 확인합니다.

```bash
darchive list
darchive pending
darchive process
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
- `process`: pending capture가 있을 때만 Codex CLI non-interactive mode로 보내 구조화된 archive metadata를 받고 SQLite에 저장합니다. pending이 없으면 Codex를 호출하지 않고 종료합니다.
- `process --no-codex`: Codex 없이 텍스트/캡션과 optional OCR fallback만 사용합니다. 로컬 점검과 테스트용입니다.
- `list`: capture 상태, 파일 다운로드 상태, archive metadata 존재 여부와 제목/요약 preview를 함께 보여줍니다.
- `show`: capture와 파일, 처리된 archive metadata를 함께 보여줍니다.

## Codex processor

`darchive process`는 기본적으로 `codex exec`를 사용합니다.

- Codex는 capture packet과 이미지 파일을 읽습니다.
- 캡처/사진은 primary input입니다. Codex prompt는 "캡처 이미지"라는 라벨이 아니라 이미지 안의 실제 핵심 내용과 의미를 추출하도록 요구합니다.
- Codex 결과는 JSON Schema로 제한됩니다.
- Python 코드가 결과를 검증한 뒤 SQLite에 씁니다.
- SQLite에는 `title`, `core_summary`, `key_points`, `context`, `raw_extracted_text`, `why_saved`, `tags`, `content_type`, `source_language`, `confidence`, `needs_review`가 저장됩니다.
- 기존 archive row 호환성을 위해 old `summary`/`extracted_text` 컬럼도 fallback 값으로 유지됩니다.
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

일반 운영에서는 launchd가 poller를 계속 켜고 processor를 5분마다 실행합니다. Processor는 먼저 SQLite에서 pending capture를 확인하고, 없으면 Codex를 호출하지 않고 종료합니다. `darchive telegram`, `darchive pending`, `darchive process` 직접 실행은 테스트/디버그용입니다.

## Troubleshooting

- `darchive list`에 아무 것도 없으면 `darchive telegram`이 실행 중인지 확인합니다.
- 그룹에서 일반 메시지나 사진이 안 잡히면 BotFather에서 Group Privacy를 끄거나 1:1 채팅으로 전환합니다.
- `HTTP Error 409: Conflict`가 로그에 있으면 같은 bot token으로 둘 이상의 polling bot이 실행 중인 상태입니다. token을 프로젝트별로 분리하거나 중복 poller를 종료합니다.
- 봇 추가/삭제 같은 Telegram 서비스 이벤트와 텍스트/캡션/파일이 없는 메시지는 capture로 저장하지 않습니다.
- `pending`이 비어 있으면 처리할 capture가 없다는 뜻입니다. 이 상태에서 scheduled processor가 실행되어도 Codex 작업은 발생하지 않습니다.

## 보안

`.env`, `.local/`, SQLite DB, 로그, 캡처 파일은 커밋하지 않습니다. Codex는 DB를 직접 수정하지 않고 구조화된 JSON만 반환합니다.

공개 전 점검:

```bash
scripts/preflight_public.sh
pytest
```
