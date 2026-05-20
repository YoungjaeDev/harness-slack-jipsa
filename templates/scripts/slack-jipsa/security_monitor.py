"""채널 멤버 변화 감지 — `--dangerously-skip-permissions` risk 완화."""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


class ChannelMemberMonitor:
    """슬랙 채널 멤버 set 을 baseline 으로 기억하고, 주기적 check 로 새 멤버 감지.

    daemon 이 --dangerously-skip-permissions 로 실행 → 채널 멤버 = 명령 실행 권한자.
    본인만 멤버여야 함. 새 멤버 join 시 즉시 슬랙 경고 + audit log.
    """

    def __init__(self, web, channel: str, log: logging.Logger | None = None):
        self.web = web
        self.channel = channel
        self.known: set[str] = set()
        self.logger = log or logger
        self._timer: threading.Timer | None = None

    def baseline(self) -> None:
        """daemon 시작 시 1회. 현재 멤버 set 저장."""
        try:
            resp = self.web.conversations_members(channel=self.channel)
            self.known = set(resp.get("members", []))
            self.logger.info("channel baseline: %d members", len(self.known))
        except Exception as e:
            self.logger.warning("baseline fetch failed: %s", e)

    def check(self) -> None:
        """현재 멤버와 baseline 비교. 새 멤버 발견 시 슬랙 경고 + known 갱신."""
        try:
            resp = self.web.conversations_members(channel=self.channel)
            current = set(resp.get("members", []))
            new = current - self.known
            if new:
                self.logger.warning("NEW CHANNEL MEMBERS: %s", new)
                try:
                    self.web.chat_postMessage(
                        channel=self.channel,
                        text=(
                            f":rotating_light: 새 채널 멤버 감지: {', '.join(sorted(new))}. "
                            f"`--dangerously-skip-permissions` 사용 중 — "
                            f"명령 실행 권한 즉시 확인 필요."
                        ),
                    )
                except Exception as e:
                    self.logger.warning("alert post failed: %s", e)
                self.known = current
        except Exception as e:
            self.logger.warning("check fetch failed: %s", e)

    def start_periodic(self, interval_sec: int = 3600) -> None:
        """interval 마다 check() 재귀 스케줄. daemon 종료 시 stop() 호출 권장."""
        if not self.known:
            self.baseline()
        else:
            self.check()
        self._timer = threading.Timer(interval_sec, self.start_periodic, args=(interval_sec,))
        self._timer.daemon = True
        self._timer.start()

    def stop(self) -> None:
        if self._timer:
            self._timer.cancel()
