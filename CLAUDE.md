# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 이 저장소가 무엇인지 먼저 이해할 것

`agent-bootstrap`은 실행되는 애플리케이션이 아니라, **Claude Code가 읽고 사용자 머신에 설치해주는 "셋업 키트"** 입니다. 즉 보통 이 저장소에서는 코드가 돌아가지 않습니다. Claude가 이 폴더의 파일들을 **읽어서** 사용자의 `~/.claude/` (또는 `%USERPROFILE%\.claude\`) 안으로 카피·치환·등록해 줍니다.

따라서 작업 종류는 보통 둘 중 하나입니다:
1. **셋업 안내 실행** — 사용자가 "SKILL.md 읽고 시작해줘" 라고 하면 [SKILL.md](SKILL.md)가 진입점. 모든 단계는 거기서 시작.
2. **키트 자체 유지보수** — 모듈 문서 수정, 검증 코드 업데이트, OS별 분기 보완.

여기에는 빌드·테스트·린트 파이프라인이 없습니다. "테스트"는 각 모듈 마지막 단계의 수동 검증입니다 (예: 슬랙 채널에 "안녕" 보내고 응답 오는지).

## 핵심 아키텍처 — 위임

`templates/` 카테고리 분류 (A 검증 코드 / B `.tmpl` 치환 / C AI 즉석 생성) 와 OS 분기 매핑표(macOS/Windows/Linux × 자동 시작·폴더 감지·시크릿 권한·Stop hook)는 [SKILL.md](SKILL.md) 의 "templates/ 안 코드의 두 종류" 섹션과 "OS별 분기 로직" 섹션이 단일 출처입니다. 같은 내용을 두 문서에 중복하면 drift 위험이 있으므로, 정의는 SKILL.md에서 보고 이 문서는 유지보수자(키트 자체를 손볼 때) 관심사만 둡니다.

키트 셋업 안내 패턴(사용자 응대 원칙·한 단계씩·시크릿 echo 금지 등)도 SKILL.md "절대 원칙" 섹션에 있습니다.

## 저장소 vs 사용자 머신의 경로 매핑

저장소에 보이는 파일들이 사용자 머신에서 사는 위치:

| 저장소 (이 폴더) | 사용자 머신 |
|------------------|-------------|
| `.env.example` | `~/.claude/secrets/slack-jipsa.env` (chmod 600) |
| `templates/lib/*.py` | `~/.claude/scripts/lib/*.py` (단 `md_to_notion.py`는 `~/.claude/hooks/`) |
| `templates/hooks/*` | `~/.claude/hooks/*` |
| `templates/scripts/slack-jipsa/daemon.py` | `~/.claude/scripts/slack-jipsa/daemon.py` |
| `templates/launchd-*.plist.tmpl` | `~/Library/LaunchAgents/com.{USERNAME}.*.plist` |
| `templates/systemd-*.tmpl` | `~/.config/systemd/user/*.service|.path` |

추가로 사용자 머신에서만 생성되는 디렉토리: `~/.claude/scripts/slack-jipsa/{logs,sessions,audit}`, `~/.claude/scripts/folder-watch/{logs,locks}`, `~/.claude/scripts/slack-jipsa-shared/`.

## daemon 내부 모듈 구조 (cleanup 후)

`templates/scripts/slack-jipsa/` 안 모듈 책임:

| 파일 | 책임 |
|------|------|
| `daemon.py` | entry point (`load_env` → `JipsaDaemon.start`). ~68줄 |
| `jipsa_daemon.py` | `JipsaDaemon` 클래스 — state + handle_message 오케스트레이션 |
| `filters.py` | 메시지 필터 (is_self / is_miri / discussion 키워드) |
| `session_storage.py` | 채널별 session_id 조회·생성·리셋 |
| `claude_invoker.py` | subprocess `claude --print` 호출 + resume fallback |
| `notion_logger.py` | 한 턴 Notion DB 적재 + 모듈 1 의존성 체크 |
| `slack_io.py` | chat_postMessage / reaction add·remove 래퍼 |
| `security_monitor.py` | 채널 멤버 변화 감지 (--dangerously-skip-permissions risk 완화) |
| `audit_logger.py` | claude --print 호출 audit log (sha256 hash + 길이만) |
| `logging_config.py` | TimedRotatingFileHandler 셋업 |

위 모듈을 수정할 때 책임 분리 원칙:
- 각 모듈 100-150 줄 이하 목표. 한 파일 = 한 책임.
- 글로벌 mutable state 금지. 인스턴스 attr + threading.RLock 으로 격리.
- 외부 라이브러리 의존 (slack_sdk, urllib) 는 `slack_io.py`, `notion_logger.py` 같은 어댑터 모듈에만 가둠.
- 새 모듈 추가 시 `jipsa_daemon.py` 의 import 순서 위에 같은 패턴으로 결합 + 테스트 파일 1:1 동반.

## 모듈 의존성

```
모듈 1 (슬랙 ↔ 클코)
   ├─→ 모듈 3 (폴더 결과를 슬랙에)  ← 모듈 2 도 필요
   └─→ 모듈 4 (노션 적재)

모듈 2 (폴더 트리거)  — 독립
```

모듈 3·4는 모듈 1의 `~/.claude/secrets/slack-jipsa.env`, `~/.claude/scripts/lib/`, `~/.claude/hooks/` 가 이미 깔려있다고 가정합니다. 사용자가 모듈 3·4를 먼저 한다고 하면 모듈 1 완료 여부를 먼저 확인하세요.

## 검증된 코드 수정해야 할 때 (드물지만)

`templates/lib/` 나 `daemon.py` 같은 검증 코드는 가능한 한 그대로 두지만, 정말 고쳐야 할 때:

1. **환경 의존성을 새로 추가하지 마세요.** 새로 필요한 값은 `.env` 변수로 노출하고 기본값을 코드 안에 둡니다 (`ENV.get('NEW_VAR', 'default')` 패턴, [daemon.py](templates/scripts/slack-jipsa/daemon.py:108) 참고).
2. **`.env.example` 와 모듈 문서를 같이 업데이트.** 새 변수는 `.env.example` 에 주석과 함께 추가하고, 어느 모듈에서 채우는지도 모듈 md에 명시.
3. **Notion DB 컬럼명은 한국어가 정답.** [daemon.py:310-321](templates/scripts/slack-jipsa/daemon.py:310) 의 `프로젝트` / `시킨 일` / `한 일` / `결과` 같은 컬럼명은 모듈 4에서 `databases.create` API로 만드는 스키마와 짝입니다. 영어로 바꾸려면 [modules/04-notion-archive.md](modules/04-notion-archive.md) DB 생성 페이로드도 같이 바꿔야 합니다.
4. **Stop hook 의 재귀 가드.** [slack-session-summary.sh:24](templates/hooks/slack-session-summary.sh:24) 의 `SLACK_HOOK_RUNNING` 환경변수 가드를 제거하면 hook 무한 루프 위험. 수정 시 보존 필수.
5. **`fcntl` import 가드.** [daemon.py:35](templates/scripts/slack-jipsa/daemon.py:35) 의 `try/except ImportError`는 Windows 호환을 위한 것. 지우지 말 것.

수정 후 가능하면 `python -m py_compile templates/scripts/slack-jipsa/daemon.py` 로 syntax는 확인. 동작 검증은 사용자 환경에서만 가능.

## 사용자 응대 원칙 (SKILL.md 의 핵심 요약)

[SKILL.md](SKILL.md) 의 "절대 원칙" 6개를 위반하지 마세요. 그 중 자주 까먹는 것:
- **한 단계씩만.** 사용자가 "1단계 됐어요" 답한 후에만 2단계.
- **에러 메시지는 당신이 해석.** "이 에러 어떻게 해요?" 하면 절대 다시 사용자에게 묻지 마세요. 진단 명령 1개 → 결과 보고 → 다음 스텝.
- **시크릿은 절대 채팅에 echo 금지.** 토큰을 사용자가 붙여넣어도 답장에 다시 출력하지 마세요. 파일에 Write 할 때만 사용.

## 알아두면 좋은 비밀

- 슬랙 daemon은 채널별로 Claude Code 세션을 유지합니다. 세션 ID는 `~/.claude/scripts/slack-jipsa/sessions/{channel}.txt` 에 저장. 사용자가 슬랙에 "리셋" / "새세션" / "reset" 보내면 daemon이 새 UUID 발급 ([daemon.py:390](templates/scripts/slack-jipsa/daemon.py:390)).
- daemon이 호출하는 `claude --print` 의 `cwd`는 `~/.claude/scripts/slack-jipsa/` 입니다 ([daemon.py:200](templates/scripts/slack-jipsa/daemon.py:200)). 거기에 별도의 `CLAUDE.md` (사용자 머신에 사용자가 직접 만드는 페르소나 규칙)가 있으면 자동 로드됨. 이 저장소의 CLAUDE.md(지금 이 파일)와는 다릅니다.
- Notion API 버전이 두 개 섞여 있습니다: DB 생성은 `2022-06-28` (스키마 단순), 런타임 upsert는 `lib/notion.py` 가 `2025-09-03` (data_source 지원) 사용. 변경 시 [modules/04-notion-archive.md](modules/04-notion-archive.md) Step 3 의 주석 참고.
- `.env`/secrets 파일은 `.gitignore` 가 `*.env` (단 `.env.example` 제외) 와 `secrets/` 를 차단합니다. 토큰이 커밋에 들어가지 않도록 새 파일 추가 시 패턴 확인.
