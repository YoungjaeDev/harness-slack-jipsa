# harness-jipsa

> **AI 가 직접 깔아주는 "내 컴퓨터에 사는 슬랙 비서·자동화 키트"**

이 키트를 Claude Code 에 던지면, Claude 가 1:1 로 안내하면서 슬랙 봇·폴더 트리거·노션 적재를 깔아줍니다. 사용자는 토큰 복붙과 클릭만 하면 됩니다.

---

## ⚠️ 셋업 전 필수 확인 — 슬랙 메시지로 컴퓨터 임의 명령 실행이 가능합니다

모듈 1·3·4 (슬랙 연동) 은 슬랙 채널의 메시지를 당신 컴퓨터에서 그대로 실행합니다 (`daemon.py`가 `claude --print --dangerously-skip-permissions --add-dir ~` 로 호출). 채널에 들어온 메시지가 파일 삭제·토큰 노출·임의 다운로드·외부 네트워크 호출을 시킬 수 있습니다.

**셋업 전 다음 3개를 모두 확인하세요**:

1. 이 봇이 작동할 슬랙 채널은 **본인 1인 비공개 채널**로 만든다
2. 슬랙 워크스페이스 admin이 본인이거나 100% 신뢰할 수 있다 (admin은 비공개 채널 임의 join 가능)
3. `.env` 파일 / `~/.claude/secrets/` 폴더를 GitHub·클립보드·다른 채팅에 절대 공유하지 않는다 (Bot Token 유출 = 해당 채널 누구나 명령 실행 가능)

위 3개 중 하나라도 NO이면 모듈 1·3·4 셋업하지 마세요. 모듈 2 (폴더 트리거) 만 OK.

---

## 4 모듈

| 모듈 | 무엇 | 시간 | 난이도 |
|------|------|------|--------|
| **1. 슬랙 ↔ 클로드 코드** | 슬랙 채널에서 클로드 코드와 대화. 메시지 → 즉시 응답. 세션 끝나면 슬랙으로 자동 보고 | 30분 | ★★ |
| **2. 폴더 트리거 자동화** | 특정 폴더에 파일 떨어뜨리면 Claude가 자동 처리 (분석/이동/요약 등) | 20분 | ★ |
| **3. 슬랙 + 폴더 합치기** | 폴더 변화 → 슬랙 알림 + 자동 처리. 위 두 모듈 결합 | 10분 | ★ |
| **4. 노션 자동 적재** (선택) | Claude Code 모든 세션 + 슬랙 대화를 노션 DB에 자동 누적. 검색·회고·아카이브 | 30분 | ★★ |

---

## 사용법

```bash
git clone https://github.com/YoungjaeDev/harness-jipsa.git
cd harness-jipsa
claude
```

이어서 Claude 에 한 줄:

```
이 폴더의 SKILL.md를 읽고 셋업을 시작해줘.
```

Claude 가 OS·모듈·환경 확인 후 단계별 진행. 한 단계 끝나면 "됐어" 답만.

> **권장**: 셋업은 폴더 생성·시크릿 파일 쓰기·서비스 등록·settings.json 편집 등 권한 승인이 필요한 도구 호출이 많습니다. 매 단계 승인 클릭을 피하려면 시작 시 `claude --dangerously-skip-permissions` 또는 세션 안에서 `/permissions` → bypassPermissions 를 선택해 주세요. 미사용 시 일부 명령은 사용자가 직접 터미널에서 실행해야 합니다.

---

## 필수 준비물

| 항목 | 비용 | 필요한 모듈 |
|------|------|------------|
| **Claude Code 구독** | Pro 이상 권장 (Opus 사용량 기준) | 모든 모듈 |
| **검증된 Claude Code 빌드** | 다음 플래그 모두 지원 필요: `hooks.Stop` · `--output-format text` · `--add-dir` · `--permission-mode bypassPermissions` · `--dangerously-skip-permissions` · `--session-id` · `--resume` · `--append-system-prompt`. 2026 초 이후의 안정 빌드 권장 | — |
| **슬랙 워크스페이스** (개인용 무료) | 무료 | 1, 3 |
| **OS** | — | macOS / Windows / Linux 모두 지원 |

> daemon 은 항상 떠있고 매 슬랙 메시지·폴더 파일마다 Anthropic API 호출. Opus 모델 + 청구 한도 인지 후 진행하세요.

---

## Windows

`templates/windows/` 의 검증된 PowerShell 스크립트를 카피 사용. Stop hook, folder-watch, register-task, daemon 부팅, cleanup 모두 검증본. Python (daemon.py, lib/*) 은 OS 독립.

---

## 기여 / Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) · [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

---

## 라이선스

MIT.

---

## Credits

- 이 repo 는 OROT (`orot.ai.service@gmail.com`) 의 `agent-bootstrap v0.1` (initial commit `56dd0be`) 기반.
- 이후 모듈 분리·테스트·인스턴스 분리·daemon cleanup·Notion 적재 갱신 등은 YoungjaeDev.
- 라이선스 표기: [LICENSE](LICENSE) 의 dual copyright 라인 참조.
