# Agent Bootstrap

> **AI가 직접 깔아주는 "내 컴퓨터에 사는 에이전트" 셋업 키트**

이 키트를 Claude Code에 던지면, Claude가 직접 1:1로 안내하면서 슬랙 봇·자동화·폴더 트리거를 깔아줍니다. 사용자는 토큰 복붙과 클릭만 하면 됩니다.

---

## ⚠️ 셋업 전 필수 확인 — 슬랙 메시지로 컴퓨터 임의 명령 실행이 가능합니다

모듈 1·3·4 (슬랙 연동) 은 슬랙 채널의 메시지를 당신 컴퓨터에서 그대로 실행합니다 (`daemon.py`가 `claude --print --dangerously-skip-permissions --add-dir ~` 로 호출). 채널에 들어온 메시지가 파일 삭제·토큰 노출·임의 다운로드·외부 네트워크 호출을 시킬 수 있습니다.

**셋업 전 다음 3개를 모두 확인하세요**:

1. 이 봇이 작동할 슬랙 채널은 **본인 1인 비공개 채널**로 만든다
2. 슬랙 워크스페이스 admin이 본인이거나 100% 신뢰할 수 있다 (admin은 비공개 채널 임의 join 가능)
3. `.env` 파일 / `~/.claude/secrets/` 폴더를 GitHub·클립보드·다른 채팅에 절대 공유하지 않는다 (Bot Token 유출 = 해당 채널 누구나 명령 실행 가능)

위 3개 중 하나라도 NO이면 모듈 1·3·4 셋업하지 마세요. 모듈 2 (폴더 트리거) 만 OK.

---

## 무엇을 깔아주나요?

이 키트는 4개 모듈로 구성됩니다. 필요한 것만 골라서 셋업하면 됩니다.

| 모듈 | 무엇 | 시간 | 난이도 |
|------|------|------|--------|
| **1. 슬랙 ↔ 클로드 코드** | 슬랙 채널에서 클로드 코드와 대화. 메시지 → 즉시 응답. 세션 끝나면 슬랙으로 자동 보고 | 30분 | ★★ |
| **2. 폴더 트리거 자동화** | 특정 폴더에 파일 떨어뜨리면 Claude가 자동 처리 (분석/이동/요약 등) | 20분 | ★ |
| **3. 슬랙 + 폴더 합치기** | 폴더 변화 → 슬랙 알림 + 자동 처리. 위 두 모듈 결합 | 10분 | ★ |
| **4. 노션 자동 적재** (선택) | Claude Code 모든 세션 + 슬랙 대화를 노션 DB에 자동 누적. 검색·회고·아카이브 | 30분 | ★★ |

---

## 진짜 핵심 — "AI가 깔아준다"는 게 뭔가요?

기존 가이드(PDF·노션 문서):
- 사람이 글을 읽고 따라함
- 막히면 끝. 에러 메시지 받아도 다음 단계 모름

이 키트:
- Claude Code에 폴더를 던지면, Claude가 **읽고** 단계별 안내 시작
- 사용자 환경(맥/윈도우)을 묻고, 환경에 맞는 명령어 생성
- 사용자가 "토큰 받았어" 하면 Claude가 **`.env` 직접 작성**
- launchd plist, stop hook 스크립트 모두 Claude가 **파일 시스템에 직접 만듦**
- 사용자는 클릭·복붙·"됐어" 답변만

---

## 사용법

### 1. 키트 다운로드

```bash
git clone https://github.com/orot-ai/agent-bootstrap.git
cd agent-bootstrap
```

또는 GitHub에서 **Code → Download ZIP**.

### 2. Claude Code 실행

키트 폴더 안에서:

```bash
claude
```

### 3. 다음 한 줄을 Claude에게 보내기

```
이 폴더의 SKILL.md를 읽고 셋업을 시작해줘.
```

Claude가 자동으로:
- 어떤 모듈부터 깔지 물어봄
- 환경 확인 (맥/윈, Claude 버전, 시스템 정보)
- 단계별 안내 시작
- 파일 생성, 권한 설정, launchd 등록 등 직접 처리

---

## 필수 준비물

| 항목 | 비용 | 필요한 모듈 |
|------|------|------------|
| **Claude Code 구독** | Pro 이상 권장 (Opus 사용량 기준) | 모든 모듈 |
| **검증된 Claude Code 빌드** | 다음 플래그 모두 지원 필요: `hooks.Stop` · `--output-format text` · `--add-dir` · `--permission-mode bypassPermissions` · `--dangerously-skip-permissions` · `--session-id` · `--resume` · `--append-system-prompt`. 2026 초 이후의 안정 빌드 권장 | — |
| **예상 월 비용 (추정 · 운영 환경 따라 다름)** | 가벼운 사용 (슬랙 일 5건 + 폴더 일 2건) 약 **$30~$80**, 헤비 (일 20건+) 약 **$100~$250**. Opus 4.x 가격 기준 단순 추정이므로 실제 청구는 본인 측정 필요 | — |
| **슬랙 워크스페이스** (개인용 무료) | 무료 | 1, 3 |
| **OS** | — | macOS / Windows / Linux 모두 지원 |

> daemon은 매일 운영되며 슬랙 메시지·폴더 파일·세션 종료마다 Anthropic API 호출. `daemon.py:195`에서 `--model opus` 사용하므로 토큰 비용이 누적될 수 있음. 사용량 제한·청구 한도 인지 후 진행하세요.
> 모든 모듈이 macOS·Windows·Linux 모두에서 작동합니다. AI가 사용자 OS를 묻고 자동으로 분기 처리합니다 (macOS=launchd, Windows=Task Scheduler + PowerShell, Linux=systemd).

---

## 이 키트의 디자인 원칙

1. **AI가 리드한다** — 사용자가 가이드를 읽는 게 아니라 AI가 가이드를 읽고 사용자를 끌고 감
2. **터미널 명령은 AI가 생성** — 사용자는 복붙만
3. **막혔을 때 환경별 분기** — 에러 메시지를 AI에게 보여주면 다음 스텝 안내
4. **시크릿은 로컬에만** — 모든 토큰은 `~/.claude/secrets/` 안에 chmod 600으로 저장. GitHub에 절대 안 올라감

---

## 폴더 구조

```
agent-bootstrap/
├── README.md              ← 지금 이 파일
├── SKILL.md               ← AI 가이드 본체 (Claude가 읽음)
├── .env.example           ← 환경변수 템플릿
├── modules/               ← 모듈별 단계별 안내 (AI가 읽음)
│   ├── 01-slack-bridge.md
│   ├── 02-folder-trigger.md
│   ├── 03-bridge-trigger.md
│   └── 04-notion-archive.md
└── templates/
    ├── lib/               ← 검증된 코드 (그대로 카피)
    │   ├── notion.py
    │   ├── slack_mrkdwn.py
    │   └── md_to_notion.py
    ├── hooks/             ← Claude Code Stop hook (그대로 카피)
    │   ├── append_turn_raw.py
    │   └── slack-session-summary.sh
    ├── scripts/slack-jipsa/
    │   └── daemon.py      ← 슬랙 ↔ 클코 daemon (그대로 카피)
    ├── launchd-daemon.plist.tmpl       ← macOS daemon 자동 시작
    ├── launchd-folder-watch.plist.tmpl ← macOS 폴더 감지
    └── systemd-*.tmpl                  ← Linux systemd 동등 파일
```

## 코드 출처

`templates/lib/`, `templates/hooks/`, `templates/scripts/` 안의 파일은 **운영 환경에서 검증된 코드 그대로**입니다. 사용자 환경에 맞춘 결합은 모두 `.env` 변수로 처리되어 코드 자체는 수정할 필요가 없습니다.

폴더 트리거 watcher (`launchd WatchPaths`, PowerShell `FileSystemWatcher`, systemd `.path` unit) 코드는 모듈 2·3 문서 안에 inline으로 들어있습니다. 이 부분은 generation 코드이므로 환경에 따라 AI가 분기 처리합니다.

## Windows 사용자

이 키트의 검증 코드는 macOS·Linux 기준입니다 (bash/Python/launchd). Windows 에서는 `templates/windows/` 의 검증본 PowerShell 스크립트를 카피해서 사용합니다 (Stop hook, folder-watch, register-task, daemon 부팅, cleanup 까지 검증본). Python 부분 (daemon.py, lib/*) 은 OS 독립이라 그대로 작동.

---

## 기여 / Contributing

기여 가이드는 [CONTRIBUTING.md](CONTRIBUTING.md), 행동 강령은 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) 참고.

---

## 라이선스

MIT. 자유롭게 가져다 쓰세요.
