# Competitive Analysis: harness-slack-jipsa

**Analysis date:** 2026-05-21
**Scope:** Open-source Slack ↔ AI-agent / Claude Code daemon bridges

---

## Overview

Seven repos were selected and compared against `harness-slack-jipsa`. They represent
the full spectrum of the space: two focus specifically on Claude Code + Slack
(mpociot, jeremylongshore), one is the largest polyglot bridge in the space
(chenhg5/cc-connect, ~10k stars), one targets the Linear/Slack issue-driven
workflow (cyrusagents/cyrus), one covers OpenAI ChatGPT in Slack with C# and
LiteDB persistence (Prographers/Slack-GPT), and two are smaller Python or MCP
bridges that share our direct architecture (nariakiiwatani/claude-slack-bridge,
tomeraitz/claude-slack-bridge). Together they give good coverage across all
eight comparison axes.

---

## Comparison Table

| Repo | Session mgmt | Retry / 429 | Permission / security | Multi-instance | External integrations | Slack event pattern | OS service registration | Test coverage | Notes |
|------|-------------|-------------|----------------------|----------------|----------------------|---------------------|------------------------|---------------|-------|
| **mpociot/claude-code-slack-bot** | Per-thread (Slack thread_ts = session key), lifetime = thread open; no expiry | Not observed in reviewed files | `--dangerously-skip-permissions` delegated to local Claude Code process; no shell ACL layer | Single daemon; no project isolation concept | None (no Notion/Linear) | Socket Mode; `app_mention` + `message.im` | None — manual `npm start`, tmux suggestion | No test files visible | 159 stars; TypeScript; most popular dedicated Claude Code Slack bot |
| **jeremylongshore/claude-code-slack-channel** | Per-thread isolation; session state machine (IDLE→ACTIVE→DRAINING); supervisor.ts 980 lines | No explicit Slack 429 handler observed in reviewed files; Socket Mode handles reconnect | Five-layer prompt-injection defense; policy-gated MCP tools; Block Kit permission relay; file exfiltration guard; bot-id allowlist | Single daemon; multi-channel fan-out within one process | None (Notion/Linear not integrated) | Socket Mode; `message` events; audit projection to originating thread | None — Bun/Node/Docker instructions only | Not visible in public repo | 24 stars; TypeScript strict; ~7,760 lines across 6 src files; most security-complete |
| **chenhg5/cc-connect** | Per-user session with auto-rotation after idle timeout; configurable inactivity threshold; `/list`, `/switch`, `/clear` slash commands | Outgoing per-platform rate limiter (goroutine-based); `RateLimiter` goroutine-leak bug fixed in v1.3.x; Slack `Retry-After` parsing not observed in reviewed files | Delegates permissions to underlying agent (Claude Code `--dangerously-skip-permissions`); no additional shell ACL observed in reviewed files | Multi-workspace mode; channel-based workspace resolution; single binary for all platforms | None (no Notion/Linear) | Platform-specific adapters (Slack Socket Mode, Feishu, DingTalk, etc.) | systemd unit via `daemon install` sub-command; no launchd or Task Scheduler | Not visible | ~10k stars; Go; broadest platform coverage (12 chat platforms, 10+ agents) |
| **cyrusagents/cyrus** | Per-issue Git worktree; one Claude Code session per Linear/GitHub/Slack issue; sessions mirrored to Cyrus cloud control plane via Agent SDK SessionStore; 13-check behavioral conformance suite | Haiku label uses Sonnet as retry fallback; no Slack 429 backoff observed in reviewed files | Runs Claude Code in isolated worktrees; no explicit shell ACL; BYOK (bring your own keys) model | Supported via config.json `projects` array; each project = separate config; managed by single `cyrus` process | Linear (native), GitHub, GitLab, Slack | Monitors Linear/GitHub/GitLab issue assignment; posts streaming updates back to issue; rich dropdown/approval interactions | tmux / pm2 / systemd (documented in SELF_HOSTING.md); no launchd or Task Scheduler | F1 test harness (controlled Linear workspace); CI badge present | 601 stars; TypeScript; most complete issue-workflow coverage |
| **Prographers/Slack-GPT** | Per-thread via LiteDB (embedded .NET NoSQL DB); thread_ts = conversation key; persistent across restarts | Not observed in reviewed files; `SlackNet` library used (handles Socket Mode reconnect) | No shell access; OpenAI API only; no `--dangerously-skip-permissions`; `-context` command for system prompt override | Single daemon only | LiteDB (embedded DB for conversation history), GitHub via Octokit.Net | Socket Mode; `app_mention` events only | Docker (`docker-compose.yml`); no systemd/launchd/Task Scheduler | Not visible; .NET xUnit could be used but no test dir found | 41 stars; C#; only project with embedded persistent DB for conversations |
| **nariakiiwatani/claude-slack-bridge** | Per-channel (channel_id = session key); no expiry documented | Not observed in reviewed files | Delegates to local Claude Code process; Mac-only design | Single daemon; Mac only | None | Socket Mode; `message` events | launchd `.plist` example provided in README | Not visible | 1 star; Python; closest architecture to ours — launchd + per-channel session |
| **tomeraitz/claude-slack-bridge** | N/A — MCP server model: session is the caller's Claude Code session, not managed by bridge | N/A — bridge is stateless between invocations | MCP `ask_human` tool; Claude Code calls the bridge mid-task; no persistent shell exposure | N/A | None | Not a traditional bot; Claude Code calls MCP server which posts to Slack and blocks waiting for reply | N/A — runs as MCP stdio subprocess inside Claude Code | Not visible | 26 stars; Python; fundamentally different interaction model (human-in-the-loop MCP, not autonomous daemon) |

> **Snapshot note**: Star counts and "not observed" entries reflect a single review pass on 2026-05-21. Star counts and feature presence may have changed since.

---

## Per-Repo Briefs

### 1. mpociot/claude-code-slack-bot

**URL:** https://github.com/mpociot/claude-code-slack-bot
**Stars:** 159
**Last push:** 2025-06-27
**Language:** TypeScript (Node.js)

**Architecture:** Slack Bolt Socket Mode app. Incoming `message` events are
dispatched to a `claude-handler.ts` module that calls the Claude Code SDK
(Node.js `@anthropic-ai/claude-code`). Session key is Slack `thread_ts`;
conversation history is held in memory — no disk persistence. A
`working-directory-manager.ts` manages per-conversation cwd.

**Strengths vs us:**
- Streaming responses: updates the Slack message in-place as Claude streams output.
- Clean TypeScript module split (handler, session, logger, types).
- Active community (159 stars, frequent PRs as of mid-2025).

**Weaknesses / gaps:**
- No retry or backoff on Slack API calls; no 429 handling.
- No OS service registration (no systemd/launchd/.ps1).
- No multi-project isolation; single daemon for the whole machine.
- No external DB or audit log; sessions evaporate on restart.
- No Notion, Linear, or audit integration.
- No unit or integration tests visible in repo.

---

### 2. jeremylongshore/claude-code-slack-channel

**URL:** https://github.com/jeremylongshore/claude-code-slack-channel
**Stars:** 24
**Last push:** 2026-05-21 (active day-of-analysis)
**Language:** TypeScript strict

**Architecture:** Six source files totalling ~7,760 lines:
`server.ts` (2,752 lines, stateful runtime), `lib.ts` (1,765 lines pure
functions), `journal.ts` (1,083 lines, hash-chained audit log),
`supervisor.ts` (980 lines, session state machine). Three runtimes:
Bun, Node.js, Docker. Session granularity = Slack thread (not channel).
An `ACCESS.md` describes a declarative allowlist for users and channels.
A five-layer prompt-injection defense is documented in the `000-docs` directory.

**Strengths vs us:**
- Hash-chained, tamper-evident audit journal written to `~/.claude/channels/slack/audit.log` — far stronger than our sha256 hash-only log.
- Formal session state machine (IDLE→ACTIVE→DRAINING) with documented transitions.
- Policy-gated MCP tools with per-channel `ChannelPolicy.audit` control.
- Block Kit permission relay: operators approve tool calls via Slack buttons.
- File exfiltration guard (cannot post `.env`, `access.json` etc. via reply tool).

**Weaknesses / gaps:**
- No Slack 429 handling found.
- No OS service file (systemd/launchd/Task Scheduler) in repo.
- No Notion, Linear, or persistent-DB integration.
- Test coverage not visible in public repo.
- Very small community (24 stars despite feature depth).

---

### 3. chenhg5/cc-connect

**URL:** https://github.com/chenhg5/cc-connect
**Stars:** 9,979
**Last push:** 2026-05-20
**Language:** Go

**Architecture:** Single Go binary that bridges 10+ AI coding agents to
12 chat platforms. Platform adapters are swappable; session management is
per-user with configurable idle-timeout rotation. A built-in Web Admin UI
(embedded in binary) provides project CRUD, session monitoring, and a
chat interface. `daemon install/start/stop` sub-commands generate a systemd
unit file on Linux.

**Strengths vs us:**
- Outgoing message rate limiter per platform (goroutine-based, fixed in v1.3.x).
- Automatic `--continue` / `--resume` fallback on reconnect.
- Idle-based session rotation (our project lacks any session expiry/GC).
- Multi-workspace channel-based workspace resolution in one binary.
- Broadest platform support by far (12 chat × 10+ agents).
- Slash commands for session control (`/list`, `/switch`, `/clear`).

**Weaknesses / gaps:**
- No Slack `Retry-After` header parsing documented (rate limiter is outgoing-side only).
- No Notion or Linear integration.
- No launchd (macOS) or Task Scheduler (Windows) service file.
- No audit log / security monitor thread.
- Test coverage not visible.

---

### 4. cyrusagents/cyrus

**URL:** https://github.com/cyrusagents/cyrus
**Stars:** 601
**Last push:** 2026-05-21
**Language:** TypeScript

**Architecture:** Issue-driven agent: monitors Linear, GitHub, GitLab, or
Slack for issues assigned to `@cyrus`, then creates an isolated Git worktree
per issue and runs a Claude Code (or Codex/Cursor/Gemini) session in that
worktree. Session transcripts are mirrored to a Cyrus cloud control plane
via the Claude Agent SDK `SessionStore` contract (13-check conformance suite).
CI badge present; F1 test framework uses a sandboxed Linear workspace.

**Strengths vs us:**
- Per-issue Git worktree isolation — far stronger than our per-channel isolation.
- Linear native integration (creates/updates issues, posts streaming comments).
- Session cloud mirror: sessions survive machine restarts and can be resumed from any host.
- CI with a real test harness (F1 framework).
- Haiku→Sonnet fallback for retry on model failure.
- Shared project config across worktrees.

**Weaknesses / gaps:**
- No Notion integration.
- No Slack 429 handling found.
- No launchd (macOS) or Task Scheduler (Windows) service documentation.
- Interaction model is issue-driven, not free-form chat (different use-case fit).
- Security monitor / member-change detection absent.
- Audit log less formal than jeremylongshore's hash-chained approach.

---

### 5. Prographers/Slack-GPT

**URL:** https://github.com/Prographers/Slack-GPT
**Stars:** 41
**Last push:** 2024-10-13
**Language:** C# (.NET 8)

**Architecture:** .NET Slack bot using `SlackNet` library with Socket Mode.
Conversation history stored in LiteDB (embedded NoSQL, schema-free). Per-thread
context keyed by `thread_ts`. Supports custom `-context` command to set a
system-message for the whole thread. Custom commands and parameter flags
parsed inline. Docker Compose support.

**Strengths vs us:**
- LiteDB persistence: conversation history survives daemon restart — our project loses in-flight state on restart.
- Splits long messages into multiple Slack posts without breaking code blocks.
- Docker Compose setup with full documentation.
- `-context` flag for per-thread system prompt override.
- GitHub integration via Octokit.Net.

**Weaknesses / gaps:**
- Uses OpenAI only (no Claude Code, no `--print` subprocess pattern).
- No retry or Slack 429 handling visible.
- No multi-project isolation.
- No Notion integration, no audit log.
- C# ecosystem is a mismatch for Python-first shops.
- Last commit Oct 2024 — possibly unmaintained.

---

### 6. nariakiiwatani/claude-slack-bridge

**URL:** https://github.com/nariakiiwatani/claude-slack-bridge
**Stars:** 1
**Last push:** 2026-05-18
**Language:** Python

**Architecture:** Closest architectural twin to our project: Python daemon,
per-channel session management (channel_id = key), local Claude Code CLI
invocation, Slack Socket Mode. README includes a launchd `.plist` example.
Very minimal codebase.

**Strengths vs us:**
- launchd `.plist` documented (same OS target as us for macOS).
- Confirms our per-channel model as a natural choice for macOS-first usage.

**Weaknesses / gaps:**
- Virtually no features beyond the minimal bridge (no Notion, no audit log, no retry, no multi-instance, no security monitor, no tests).
- 1 star — effectively a personal tool.
- No Windows or Linux service registration.

---

### 7. tomeraitz/claude-slack-bridge

**URL:** https://github.com/tomeraitz/claude-slack-bridge
**Stars:** 26
**Last push:** 2026-05-20
**Language:** Python

**Architecture:** MCP server (`ask_human` tool) — fundamentally different from
autonomous daemon bridges. Claude Code calls the MCP server mid-task when it
needs a human answer. The MCP server posts a question to Slack and blocks until
a reply arrives. No persistent daemon; no session management; no autonomous
message listening.

**Strengths vs us:**
- Human-in-the-loop model is safer: Claude Code only calls out when explicitly asking a question, not on every message.
- Stateless design is simple and has no session-GC problem.
- Works with any Claude Code version that supports MCP stdio.

**Weaknesses / gaps:**
- Not an autonomous daemon: Claude Code must already be running locally.
- No Notion, no audit log, no OS service, no multi-instance, no tests.
- Different problem space (tool for interactive sessions, not a remote bridge).

---

## Patterns We Should Consider Adopting

1. **Session idle-timeout and garbage collection** — `chenhg5/cc-connect` (https://github.com/chenhg5/cc-connect) implements configurable idle-rotation: after N minutes of silence the next message silently spawns a new session without deleting the old one. Our project has no session expiry or GC; long-lived channels accumulate stale session files.

2. **Hash-chained audit journal to disk** — `jeremylongshore/claude-code-slack-channel` (https://github.com/jeremylongshore/claude-code-slack-channel) writes a hash-chained, tamper-evident log (`~/.claude/channels/slack/audit.log`) that is ratcheted per-entry. Our `audit_logger.py` records only length and sha256 of each prompt; adopting the chain-of-hashes pattern would make audit logs verifiable against post-hoc tampering.

3. **Slack 429 / `Retry-After` header handling with exponential backoff** — No surveyed project handles this explicitly at the code level (all delegate to SDK defaults), but the gap is acknowledged in community issues for `zeroclaw-labs/zeroclaw` (https://github.com/zeroclaw-labs/zeroclaw/issues/1839) and `slackapi/java-slack-sdk` (https://github.com/slackapi/java-slack-sdk/issues/64). Our project similarly lacks this. The `slack_sdk` Python library exposes `retry_handlers` on `WebClient`; implementing a `RateLimitErrorRetryHandler` with exponential backoff + jitter would close the gap without third-party dependencies.

4. **Per-thread (not per-channel) session granularity** — Both `mpociot/claude-code-slack-bot` (https://github.com/mpociot/claude-code-slack-bot) and `jeremylongshore/claude-code-slack-channel` (https://github.com/jeremylongshore/claude-code-slack-channel) key sessions on Slack `thread_ts` rather than `channel_id`. This allows parallel conversations within one channel to remain isolated. Our per-channel model forces all messages in a channel to share one Claude Code session, which can be limiting for team channels.

5. **Persistent conversation history across daemon restarts** — `Prographers/Slack-GPT` (https://github.com/Prographers/Slack-GPT) uses LiteDB to persist conversation context. Our project holds no conversation history in Notion or on disk (Notion stores summaries only); a restart wipes context. A lightweight SQLite store (via Python's built-in `sqlite3`) for recent turns per channel would survive daemon restarts and could double as the audit log.

6. **Formal session state machine** — `jeremylongshore/claude-code-slack-channel` (https://github.com/jeremylongshore/claude-code-slack-channel) documents a formal IDLE→ACTIVE→DRAINING state machine in `supervisor.ts`. Our `jipsa_daemon.py` manages state via instance attributes and a `threading.RLock` but has no explicit state enum, making unexpected state transitions harder to detect and test.

7. **Git worktree isolation per task** — `cyrusagents/cyrus` (https://github.com/cyrusagents/cyrus) creates a fresh Git worktree per Linear/GitHub issue, so parallel tasks never share uncommitted working-tree state. For our project-mode instances this would prevent concurrent sessions in the same project from racing on the same working tree, which is a realistic risk when two Slack users trigger Claude Code simultaneously in a project channel.
