"""JipsaDaemon: 슬랙↔클로드 코드 daemon 클래스.

글로벌 mutable state 를 인스턴스 attr 로 격리. handle_message 오케스트레이션은
filters / claude_invoker / notion_logger / slack_io / shared_buffer 모듈 함수 위임.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any

from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

import filters
import shared_buffer
import slack_io
from audit_logger import AuditLogger
from claude_invoker import call_claude
from notion_logger import notion_log_turn
from security_monitor import ChannelMemberMonitor
from session_storage import get_or_create_session, reset_session

logger = logging.getLogger("jipsa.daemon")

RESET_KEYWORDS = {"리셋", "새세션", "새 세션", "reset", "!reset", "!리셋"}


class JipsaDaemon:
    """슬랙↔클로드 코드 daemon. instance state 로 글로벌 격리."""

    DIALOG_TURN_LIMIT = 6

    def __init__(self, env: dict, sessions_dir: Path, logs_dir: Path,
                 shared_dir: Path, secrets_path: Path, system_prompt: str,
                 audit_dir: Path | None = None):
        self.env = env
        self.sessions_dir = sessions_dir
        self.logs_dir = logs_dir
        self.shared_dir = shared_dir
        self.secrets_path = secrets_path
        self.system_prompt = system_prompt

        self.bot_token = env["SLACK_BOT_TOKEN"]
        self.app_token = env["SLACK_APP_TOKEN"]
        self.channel = env["SLACK_CHANNEL"]
        self.channel_dialog = env.get("SLACK_CHANNEL_DIALOG", "")
        self.miri = env.get("USER_SLACK_ID") or env.get("MIRI_USER_ID", "")
        self.user_name = env.get("USER_NAME", "사용자")
        self.bot_name = env.get("SLACK_BOT_NAME", "슬랙 비서")
        self.notion_session_db = env.get("NOTION_SESSION_DB", "")
        self.notion_daily_db = env.get("NOTION_DAILY_DB", "")
        self.claude_timeout = int(env.get("CLAUDE_TIMEOUT_SEC", "900"))

        self.web = slack_io.make_web_client(self.bot_token)
        self.bot = self._resolve_bot_user_id(env.get("BOT_USER_ID", "").strip())
        self.sock = SocketModeClient(app_token=self.app_token, web_client=self.web)

        # Mutable state — locked
        self.state_lock = threading.RLock()
        self.dialog_self_turn_count = 0
        self.discussion_mode: dict[str, bool] = {}
        self.discussion_state_file = self.shared_dir / "discussion_state.json"

        # Audit + security monitor (Phase E)
        self.audit = AuditLogger(audit_dir or (self.logs_dir.parent / "audit"))
        self.member_monitor = ChannelMemberMonitor(self.web, self.channel, logger)

    # -------- Bot identity resolution --------
    def _resolve_bot_user_id(self, current: str) -> str:
        """BOT_USER_ID 가 비어있으면 auth.test → .env write-back."""
        if current:
            return current
        try:
            bot = self.web.auth_test()["user_id"]
            text = self.secrets_path.read_text()
            if "BOT_USER_ID=" in text:
                new = re.sub(r"(?m)^BOT_USER_ID=.*$", f"BOT_USER_ID={bot}", text)
            else:
                new = text.rstrip() + f"\nBOT_USER_ID={bot}\n"
            self.secrets_path.write_text(new)
            logger.info("auto-resolved BOT_USER_ID=%s", bot)
            return bot
        except Exception as e:
            logger.warning("BOT_USER_ID auth.test failed: %s", e)
            return ""

    # -------- Discussion state persistence --------
    def _write_discussion_state(self) -> None:
        try:
            with self.state_lock:
                snapshot = dict(self.discussion_mode)
            self.discussion_state_file.write_text(
                json.dumps({"mode": snapshot, "ts": time.time()})
            )
        except Exception as e:
            logger.warning("discussion_state write failed: %s", e)

    # -------- Filters & dispatch helpers --------
    def _apply_filters(self, event: dict) -> tuple[bool, dict] | None:
        text = (event.get("text") or "").strip()
        channel = event.get("channel", "")
        ts = event.get("ts", "")
        user = event.get("user", "")
        bot_id = event.get("bot_id", "")

        if not text:
            return None
        if channel != self.channel and channel != self.channel_dialog:
            return None

        is_dialog = (channel == self.channel_dialog)
        is_miri = filters.is_miri(event, self.miri)
        is_self = filters.is_self(event, self.bot) or (bot_id == self.bot)
        is_other_bot = (
            not is_miri and not is_self
            and user.startswith("U") and user != self.miri
        )

        if is_self:
            return None
        if not is_dialog and not is_miri:
            return None

        return is_dialog, {
            "channel": channel, "ts": ts, "text": text,
            "is_miri": is_miri, "is_other_bot": is_other_bot,
            "thread_ts": event.get("thread_ts", ""),
        }

    def _toggle_discussion(self, channel: str, text: str) -> None:
        with self.state_lock:
            if filters.matches_discussion_stop(text):
                self.discussion_mode[channel] = False
                logger.info("discussion mode OFF (stop keyword)")
            elif filters.matches_discussion_trigger(text):
                self.discussion_mode[channel] = True
                self.dialog_self_turn_count = 0
                logger.info("discussion mode ON (trigger keyword)")
            else:
                was_on = self.discussion_mode.get(channel, False)
                self.discussion_mode[channel] = False
                self.dialog_self_turn_count = 0
                if was_on:
                    logger.info("discussion mode OFF (new topic from user)")
        self._write_discussion_state()

    def _check_other_bot_continue(self, channel: str) -> bool:
        with self.state_lock:
            if not self.discussion_mode.get(channel):
                logger.info("other-bot, discussion OFF — skip")
                return False
            if self.dialog_self_turn_count >= self.DIALOG_TURN_LIMIT:
                logger.info("dialog turn limit — auto-stop")
                self.discussion_mode[channel] = False
                self._write_discussion_state()
                return False
        return True

    def _build_prompt(self, channel: str, thread_ts: str, text: str) -> str:
        shared = shared_buffer.load(self.shared_dir, channel, thread_ts)
        if not shared or len(shared) <= 1:
            return text
        ctx_lines = [f"## 최근 대화 맥락 ({self.user_name}·Claude·다른 봇 모두 포함)"]
        for h in shared[-15:-1]:
            ctx_lines.append(f"[{h.get('who','?')}] {h.get('text','')[:400]}")
        ctx_lines.append("")
        ctx_lines.append("## 현재 메시지")
        ctx_lines.append(text)
        return "\n".join(ctx_lines)

    def _who_label(self, ctx: dict) -> str:
        if ctx["is_miri"]:
            return self.user_name
        if ctx["is_other_bot"]:
            return "other-bot"
        return "?"

    def _audit_callback(self, prompt: str):
        def _cb(ch, sid, lin, lout):
            self.audit.log_invocation(
                channel=ch, session_id=sid, prompt=prompt,
                result_len=lout, status=("ok" if lout > 0 else "fail"),
            )
        return _cb

    def _handle_reply(self, channel: str, ts: str, thread_ts: str,
                      reply: str) -> str | None:
        """슬랙에 게시한 텍스트 (to_mrkdwn 변환 후) 를 리턴. SKIP/empty/FAIL → None.

        리턴값은 Notion 적재본을 슬랙·shared_buffer 본문과 동기화하기 위해 사용.
        """
        if reply.strip().upper().startswith("SKIP"):
            logger.info("SKIP — other bot's turn")
            slack_io.swap_reaction(self.web, channel, ts, "hourglass_flowing_sand", "eyes")
            return None

        if not reply.strip() or reply.strip() == "__SILENT_FAIL__":
            is_fail = reply.strip() == "__SILENT_FAIL__"
            logger.info("empty/fail reply (fail=%s)", is_fail)
            slack_io.swap_reaction(
                self.web, channel, ts, "hourglass_flowing_sand",
                "warning" if is_fail else "speech_balloon",
            )
            return None

        try:
            from lib.slack_mrkdwn import to_mrkdwn
            reply_clean = to_mrkdwn(reply)
        except Exception:
            reply_clean = reply

        # 1) thread_ts 가 있는 메시지는 같은 스레드에 응답해야 함 (없으면 채널 루트로 빠짐).
        # 2) post_message 실패 (res falsy) 시 Slack 엔 아무것도 안 올라간 상태이므로
        #    shared_buffer / Notion 에도 기록하면 안 됨. warning reaction 으로 알리고 None 반환.
        res = slack_io.post_message(
            self.web, channel, reply_clean,
            thread_ts=thread_ts or None,
        )
        if not res:
            slack_io.swap_reaction(
                self.web, channel, ts, "hourglass_flowing_sand", "warning",
            )
            return None

        if channel == self.channel_dialog:
            with self.state_lock:
                self.dialog_self_turn_count += 1

        shared_buffer.append(
            self.shared_dir, channel, thread_ts, "클코", reply_clean,
            msg_ts=str(res.get("ts", "") or ""),
        )

        slack_io.swap_reaction(self.web, channel, ts, "hourglass_flowing_sand",
                               "white_check_mark")
        return reply_clean

    # -------- Message handler (dispatcher) --------
    def handle_message(self, event: dict) -> None:
        ctx = self._apply_filters(event)
        if ctx is None:
            return
        is_dialog, c = ctx

        if is_dialog and c["is_miri"]:
            self._toggle_discussion(c["channel"], c["text"])

        if c["is_other_bot"]:
            shared_buffer.append(
                self.shared_dir, c["channel"], c["thread_ts"],
                "other-bot", c["text"], msg_ts=c["ts"],
            )
            if not self._check_other_bot_continue(c["channel"]):
                return

        if c["text"].lower() in RESET_KEYWORDS:
            new_sid = reset_session(c["channel"], self.sessions_dir)
            slack_io.post_message(
                self.web, c["channel"], f"🔄 새 세션 시작 (`{new_sid[:8]}`)",
            )
            return

        logger.info("msg: %s", c["text"][:80])

        slack_io.add_reaction(self.web, c["channel"], c["ts"], "hourglass_flowing_sand")
        shared_buffer.append(
            self.shared_dir, c["channel"], c["thread_ts"],
            self._who_label(c), c["text"], msg_ts=c["ts"],
        )

        prompt = self._build_prompt(c["channel"], c["thread_ts"], c["text"])
        reply = call_claude(
            prompt, c["channel"],
            sessions_dir=self.sessions_dir,
            system_prompt=self.system_prompt,
            timeout=self.claude_timeout,
            on_invoke=self._audit_callback(prompt),
        )
        logger.info("reply: %s", reply[:80])
        posted = self._handle_reply(c["channel"], c["ts"], c["thread_ts"], reply)
        if posted is None:
            return

        try:
            sid_for_log, _ = get_or_create_session(c["channel"], self.sessions_dir)
            threading.Thread(
                target=notion_log_turn,
                args=(c["channel"], c["ts"], c["text"], posted, sid_for_log, "opus"),
                kwargs={
                    "session_db": self.notion_session_db,
                    "daily_db": self.notion_daily_db,
                    "bot_name": self.bot_name,
                },
                daemon=True,
            ).start()
        except Exception as e:
            logger.warning("notion log thread fail: %s", e)

    # -------- Socket Mode event entry --------
    def on_event(self, client: SocketModeClient, req: SocketModeRequest) -> None:
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        if req.type != "events_api":
            return
        event = (req.payload or {}).get("event", {})
        if event.get("type") == "message" and not event.get("subtype"):
            threading.Thread(target=self.handle_message, args=(event,), daemon=True).start()

    # -------- Lifecycle --------
    def start(self) -> None:
        """daemon 시작. member monitor + sock 연결."""
        try:
            raw_interval = self.env.get("SECURITY_MONITOR_INTERVAL", "3600")
            try:
                interval = int(raw_interval)
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid SECURITY_MONITOR_INTERVAL=%r, using default 3600",
                    raw_interval,
                )
                interval = 3600
            if interval <= 0:
                logger.warning(
                    "SECURITY_MONITOR_INTERVAL must be positive, using default 3600",
                )
                interval = 3600
            self.member_monitor.start_periodic(interval_sec=interval)
        except Exception as e:
            logger.warning("member monitor start failed: %s", e)
        self.sock.socket_mode_request_listeners.append(self.on_event)
        self.sock.connect()
        logger.info("JipsaDaemon started (channel=%s)", self.channel)
