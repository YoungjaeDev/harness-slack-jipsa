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

from slack_sdk import WebClient
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

        self.web = WebClient(token=self.bot_token)
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

    def _handle_reply(self, channel: str, ts: str, thread_ts: str, reply: str) -> None:
        if reply.strip().upper().startswith("SKIP"):
            logger.info("SKIP — other bot's turn")
            slack_io.swap_reaction(self.web, channel, ts, "hourglass_flowing_sand", "eyes")
            return

        if not reply.strip() or reply.strip() == "__SILENT_FAIL__":
            is_fail = reply.strip() == "__SILENT_FAIL__"
            logger.info("empty/fail reply (fail=%s)", is_fail)
            slack_io.swap_reaction(
                self.web, channel, ts, "hourglass_flowing_sand",
                "warning" if is_fail else "speech_balloon",
            )
            return

        try:
            from lib.slack_mrkdwn import to_mrkdwn
            reply_clean = to_mrkdwn(reply)
        except Exception:
            reply_clean = reply

        res = slack_io.post_message(self.web, channel, reply_clean)
        if res and channel == self.channel_dialog:
            with self.state_lock:
                self.dialog_self_turn_count += 1

        if res:
            shared_buffer.append(
                self.shared_dir, channel, thread_ts, "클코", reply_clean,
                msg_ts=str(res.get("ts", "") or ""),
            )

        slack_io.swap_reaction(self.web, channel, ts, "hourglass_flowing_sand",
                               "white_check_mark")

    # -------- Message handler --------
    def handle_message(self, event: dict) -> None:
        """사용자 메시지 처리 + (대화 채널이면) 다른 봇 메시지에도 반응."""
        text = (event.get("text") or "").strip()
        channel = event.get("channel", "")
        ts = event.get("ts", "")
        user = event.get("user", "")
        bot_id = event.get("bot_id", "")

        if not text:
            return
        if channel != self.channel and channel != self.channel_dialog:
            return

        is_dialog = (channel == self.channel_dialog)
        is_miri = filters.is_miri(event, self.miri)
        is_self = filters.is_self(event, self.bot) or (bot_id == self.bot)
        is_other_bot = (
            not is_miri and not is_self
            and user.startswith("U") and user != self.miri
        )

        if is_self:
            return
        if not is_dialog and not is_miri:
            return

        # Discussion mode (사용자 발화 기준 ON/OFF)
        if is_dialog and is_miri:
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

        # Other-bot 발화: discussion 모드 켜진 경우에만 응답
        if is_other_bot:
            thread_ts_only = event.get("thread_ts", "")
            shared_buffer.append(self.shared_dir, channel, thread_ts_only,
                                 "other-bot", text, msg_ts=ts)
            with self.state_lock:
                if not self.discussion_mode.get(channel):
                    logger.info("other-bot message, discussion OFF — skip response")
                    return
                if self.dialog_self_turn_count >= self.DIALOG_TURN_LIMIT:
                    logger.info("dialog turn limit (%d) — auto-stop discussion",
                                self.DIALOG_TURN_LIMIT)
                    self.discussion_mode[channel] = False
                    self._write_discussion_state()
                    return
                turn = self.dialog_self_turn_count
            logger.info("discussion ON — respond to other-bot (turn %d/%d)",
                        turn, self.DIALOG_TURN_LIMIT)

        # 명령어: 리셋 / 새세션 / reset
        if text.strip().lower() in ("리셋", "새세션", "새 세션", "reset", "!reset", "!리셋"):
            new_sid = reset_session(channel, self.sessions_dir)
            slack_io.post_message(self.web, channel, f"🔄 새 세션 시작 (`{new_sid[:8]}`)")
            return

        logger.info("msg: %s", text[:80])

        # ⏳ reaction
        slack_io.add_reaction(self.web, channel, ts, "hourglass_flowing_sand")

        thread_ts = event.get("thread_ts", "")
        who_label = self.user_name if is_miri else ("other-bot" if is_other_bot else "?")
        shared_buffer.append(self.shared_dir, channel, thread_ts, who_label,
                             text, msg_ts=ts)

        # 공유 버퍼 → prompt prefix (cross-channel 맥락)
        shared = shared_buffer.load(self.shared_dir, channel, thread_ts)
        prompt_with_ctx = text
        if shared and len(shared) > 1:
            ctx_lines = [f"## 최근 대화 맥락 ({self.user_name}·Claude·다른 봇 모두 포함)"]
            for h in shared[-15:-1]:
                ctx_lines.append(f"[{h.get('who','?')}] {h.get('text','')[:400]}")
            ctx_lines.append("")
            ctx_lines.append("## 현재 메시지")
            ctx_lines.append(text)
            prompt_with_ctx = "\n".join(ctx_lines)

        # 클로드 호출
        reply = call_claude(
            prompt_with_ctx, channel,
            sessions_dir=self.sessions_dir,
            system_prompt=self.system_prompt,
            timeout=self.claude_timeout,
            on_invoke=lambda ch, sid, lin, lout: self.audit.log_invocation(
                channel=ch, session_id=sid, prompt=prompt_with_ctx,
                result_len=lout, status=("ok" if lout > 0 else "fail"),
            ),
        )
        logger.info("reply: %s", reply[:80])

        # SKIP 응답 (다른 봇이 응답할 차례)
        if reply.strip().upper().startswith("SKIP"):
            logger.info("SKIP — other bot's turn")
            slack_io.swap_reaction(self.web, channel, ts, "hourglass_flowing_sand", "eyes")
            return

        # 빈 응답 또는 silent fail → reaction 만
        if not reply.strip() or reply.strip() == "__SILENT_FAIL__":
            is_fail = reply.strip() == "__SILENT_FAIL__"
            logger.info("empty/fail reply — no slack send (fail=%s)", is_fail)
            slack_io.swap_reaction(
                self.web, channel, ts, "hourglass_flowing_sand",
                "warning" if is_fail else "speech_balloon",
            )
            return

        # 마크다운 정리
        try:
            from lib.slack_mrkdwn import to_mrkdwn
            reply_clean = to_mrkdwn(reply)
        except Exception:
            reply_clean = reply

        res = slack_io.post_message(self.web, channel, reply_clean)
        if res and channel == self.channel_dialog:
            with self.state_lock:
                self.dialog_self_turn_count += 1

        if res:
            shared_buffer.append(self.shared_dir, channel, thread_ts, "클코",
                                 reply_clean, msg_ts=str(res.get("ts", "") or ""))

        # ⏳ → ✅
        slack_io.swap_reaction(self.web, channel, ts, "hourglass_flowing_sand",
                               "white_check_mark")

        # 노션 로그 비동기
        try:
            sid_for_log, _ = get_or_create_session(channel, self.sessions_dir)
            threading.Thread(
                target=notion_log_turn,
                args=(channel, ts, text, reply_clean, sid_for_log, "opus"),
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
            self.member_monitor.start_periodic(interval_sec=3600)
        except Exception as e:
            logger.warning("member monitor start failed: %s", e)
        self.sock.socket_mode_request_listeners.append(self.on_event)
        self.sock.connect()
        logger.info("JipsaDaemon started (channel=%s)", self.channel)
