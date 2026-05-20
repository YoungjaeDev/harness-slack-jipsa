"""채널 멤버 변화 감지 — Phase E.1 본구현 예정. 현재는 noop stub."""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


class ChannelMemberMonitor:
    """Phase E.1 에서 멤버 baseline + check + 슬랙 경고 본구현 예정.
    현재는 import 호환을 위한 noop stub.
    """

    def __init__(self, web, channel: str, log: logging.Logger | None = None):
        self.web = web
        self.channel = channel
        self.known: set[str] = set()
        self.logger = log or logger
        self._timer: threading.Timer | None = None

    def baseline(self) -> None:
        pass

    def check(self) -> None:
        pass

    def start_periodic(self, interval_sec: int = 3600) -> None:
        pass

    def stop(self) -> None:
        if self._timer:
            self._timer.cancel()
