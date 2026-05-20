# 기여 가이드

harness-jipsa 에 관심 가져주셔서 감사합니다. 본 문서는 한국어 화자 기여자 대상입니다.

## 시작하기

1. **이슈 먼저**
   기능 추가·아키텍처 변경은 PR 전에 GitHub Issue 에 의도를 남겨주세요.
   사소한 오타·로그 메시지 수정은 바로 PR 환영.

2. **로컬 환경 구성**
   ```powershell
   git clone https://github.com/YoungjaeDev/harness-jipsa.git
   cd harness-jipsa
   uv sync --extra test
   uv run pytest tests/ -q
   ```
   Windows / macOS / Linux 모두 지원. CI 가 3 OS × 3 Python 버전 매트릭스 검증.

## 코드 스타일

- **검증 코드 (A 카테고리) 는 손대지 마세요.**
  `templates/lib/*.py`, `templates/scripts/slack-jipsa/*.py` 의 검증된 코드는
  사용자 환경에서 실측된 코드입니다. 버그 발견 시 이슈 → 합의 후 수정.
- **B 카테고리 (`.tmpl`)**: 치환 토큰 (`{USERNAME}`, `{HOME}`) 보존.
- **C 카테고리 (Windows 검증본 PS1)**: AST parse 통과 필수 (CI lint 워크플로우가 자동 검증).
- 새 의존성 추가는 `pyproject.toml` 의 `[project.optional-dependencies].test` 에 명시.
- 한국어 코멘트·문서가 기본. 영어 fallback 없음.

## PR 절차

1. **브랜치 네이밍**: `feat/<short-desc>`, `fix/<short-desc>`, `docs/<short-desc>`, `cleanup/<date>` 등.
2. **커밋 컨벤션** (Conventional Commits):
   - `feat:` 새 기능
   - `fix:` 버그 수정
   - `refactor:` 리팩터링 (외부 동작 변화 없음)
   - `test:` 테스트 추가/수정
   - `docs:` 문서만 변경
   - `ci:` CI 설정
   - `chore:` 잡일
3. **테스트**:
   - 새 코드는 `tests/unit/` 또는 `tests/integration/` 에 테스트 추가.
   - 기존 테스트가 깨지면 안 됨.
4. **CI 통과**:
   - GHA `tests` + `lint` 두 워크플로우 모두 green.
5. **PR 본문**:
   - 무엇을·왜·어떻게 변경했는지 요약.
   - 관련 이슈 번호 (`Closes #N`).
   - 수동 검증 단계 (UI 변경 또는 외부 API 호출 시).

## 이슈 작성

다음 정보를 포함해주세요:

- **환경**: OS (Windows/macOS/Linux), Python 버전, harness-jipsa 커밋 해시
- **재현 단계**: 1-2-3
- **기대 동작 / 실제 동작**
- **로그 첨부** (`.env` 의 토큰·시크릿은 반드시 `***` 로 마스킹)

## 의사 결정

- **사소한 변경** (오타·로그 메시지·테스트 추가): PR 바로 환영.
- **큰 변경** (새 모듈 추가·기존 구조 리팩터·외부 API 추가): 이슈 → 메인테이너 코멘트 후 PR.
- **보안 보고**: GitHub Security Advisory 또는 메인테이너 이메일 직접 (공개 이슈에 올리지 말 것).

## Code of Conduct

본 프로젝트는 [Contributor Covenant 2.1](CODE_OF_CONDUCT.md) 을 따릅니다.
참여 전 한 번 읽어주세요.

## 기타

질문은 GitHub Issue 의 `question` 라벨에 자유롭게 올려주세요.
