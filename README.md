# 다카이브봇

다카이브봇은 나중에 다시 보고 싶은 글, 캡처, 사진, 메모를 Telegram으로 보내 두면 관심사별로 모아 정리해 주는 개인 아카이브 봇입니다.

핵심은 "저장"보다 "다시 쓸 수 있게 정리"하는 것입니다. 특히 스크린샷 안에 들어 있는 글의 핵심 내용, 중요한 포인트, 어떤 관심사에 가까운지, 왜 저장해 둘 만한지까지 구조화해서 로컬에 남기는 것을 목표로 합니다.

## 어떤 프로젝트인가

다카이브봇은 Telegram 채팅방을 개인 수집함처럼 쓰는 로컬 아카이브 프로젝트입니다. 웹에서 본 글, 소셜 피드 캡처, 읽다가 남겨두고 싶은 문장, 나중에 다시 생각해 보고 싶은 아이디어를 봇에게 보내면 원본과 정리 결과가 내 컴퓨터에 쌓입니다.

일반적인 북마크나 갤러리처럼 파일만 모으는 것이 아니라, 각 캡처가 어떤 관심사에 속하는지와 다시 볼 만한 이유를 함께 남깁니다. 시간이 지나면 흩어진 캡처들이 AI, 커리어, 테크놀로지, 스포츠 같은 관심사별 아카이브가 되고, 이후에는 서로 관련된 캡처와 반복되는 주제를 찾아 인사이트로 발전시킬 수 있습니다.

## 아카이브가 쌓이는 과정

1. Telegram에서 다카이브봇과 1:1 채팅을 엽니다.
2. 나중에 다시 보고 싶은 캡처나 사진을 보냅니다.
3. 다카이브봇이 원본 메시지와 파일을 로컬에 저장합니다.
4. 예약된 processor가 새 항목만 골라 핵심 내용과 관심사 분류를 정리합니다.
5. 필요할 때 로컬에서 목록과 상세 내용을 확인합니다.

## 어떻게 작동하나

다카이브봇은 두 단계로 움직입니다.

첫 번째는 수집입니다. Telegram poller가 허용된 채팅에서 새 메시지를 확인하고, 텍스트와 캡션, 사진, 문서를 로컬 SQLite DB와 `.local/captures/` 폴더에 저장합니다. Telegram에만 의존하지 않도록 원본 파일도 로컬에 내려받습니다.

두 번째는 정리입니다. 예약된 processor가 주기적으로 SQLite에서 아직 정리되지 않은 항목만 찾습니다. 처리할 항목이 없으면 아무 작업 없이 종료하고, 처리할 항목이 있으면 Codex가 캡처와 이미지 내용을 읽어 구조화된 JSON을 반환합니다. Python 코드는 그 JSON을 검증한 뒤 SQLite에 저장합니다. Codex는 DB를 직접 수정하지 않습니다.

이 구조 덕분에 다카이브봇은 조용히 돌아가면서도 원본 보관, 관심사 분류, 요약, 나중에 다시 볼 이유를 분리해서 남길 수 있습니다.

## 로컬 아카이브에 정리되는 내용

다카이브봇은 Telegram으로 보낸 캡처와 메시지를 로컬 폴더와 SQLite DB에 저장하고, 나중에 찾아보기 쉬운 형태로 정리합니다.

- 원본 메시지와 첨부 파일은 로컬에 보관합니다.
- 제목과 핵심 요약으로 목록에서 빠르게 알아볼 수 있게 합니다.
- AI, 커리어, 테크놀로지, 스포츠 같은 관심사와 세부 주제로 분류합니다.
- 주요 포인트와 원문 텍스트를 함께 남겨 다시 읽기 쉽게 합니다.
- 저장 이유, 다시 볼 우선순위, 태그를 붙여 나중에 검색하거나 분류할 수 있게 합니다.
- 나중에 다른 캡처와 연결될 수 있는 작은 insight seed를 남깁니다.
- 처리할 새 항목이 없으면 scheduled processor는 조용히 종료합니다.

## 빠른 시작

```bash
cd /Users/hennei/workspace/darchivebot
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
darchive init
darchive doctor
```

개인 아카이브 용도는 Telegram 그룹보다 봇과의 1:1 채팅을 권장합니다. 설정이 단순하고, 다른 대화와 섞이지 않아 캡처함으로 쓰기 좋습니다.

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

## 주요 명령어

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

- `telegram`: Telegram에서 보낸 글, 캡처, 사진, 문서를 로컬에 저장합니다.
- `pending`: 아직 정리되지 않은 항목과 처리 계획을 미리 봅니다.
- `process`: 새 항목이 있을 때만 내용을 정리하고 로컬 DB에 저장합니다.
- `process --no-codex`: Codex 없이 기본 추출만 실행합니다. 로컬 점검과 테스트용입니다.
- `list`: 최근 캡처와 정리 상태를 한 줄씩 확인합니다.
- `list --interest <interest>`: 특정 관심사로 정리된 항목만 확인합니다.
- `show`: 캡처 원본, 파일 경로, 정리된 제목/요약/포인트를 자세히 확인합니다.

## 정리되는 내용

다카이브봇은 단순히 "이미지를 저장했다"에서 끝나지 않고, 나중에 검색하고 다시 읽기 좋은 형태로 정리합니다.

- 제목: 나중에 목록에서 알아보기 쉬운 짧은 이름
- 핵심 요약: 캡처나 글이 말하는 실제 내용
- 주요 포인트: 중요한 주장, 사실, 관찰, 아이디어
- 관심사와 주제: AI, 커리어, 스포츠처럼 나중에 묶어 볼 기준
- 원문 텍스트: 이미지나 메시지에서 읽힌 텍스트
- 다시 볼 이유와 우선순위: 왜 나중에 다시 볼 만한지
- insight seed: 나중에 비슷한 항목들과 연결될 수 있는 작은 단서
- 태그와 언어 정보: 검색과 분류를 위한 보조 정보

기술적으로는 Codex가 캡처와 이미지를 읽어 구조화된 JSON을 만들고, Python 코드가 검증한 뒤 SQLite에 저장합니다. Codex가 DB를 직접 수정하지는 않습니다.

## 주요 설정

```env
DARCHIVE_CODEX_ENABLED=true
DARCHIVE_CODEX_BIN=codex
DARCHIVE_CODEX_MODEL=
DARCHIVE_CODEX_SANDBOX=read-only
DARCHIVE_CODEX_EPHEMERAL=true
DARCHIVE_CODEX_TIMEOUT_SEC=900
```

## 앞으로 더해질 수 있는 것

다카이브봇은 먼저 캡처와 글을 안정적으로 모으고 관심사별로 정리하는 개인 아카이브로 시작합니다. 이후에는 저장된 항목 사이의 관련성, 반복되는 관심사, 주간/월간 인사이트, Telegram으로 다시 꺼내보기 같은 기능을 붙일 수 있습니다.

Insight synthesis 방향은 [docs/insight-synthesis.md](docs/insight-synthesis.md)에 따로 정리합니다.

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
