"""Latest WhatsApp notification, for the layout's WhatsApp page.

Notifications are captured by a monitor (minitela.sources.notifications_gio) and pushed
here; this module decides which ones are from WhatsApp and how they are shown.
"""

import html
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

from minitela.protocol import tags
from minitela.sources.base import Source, Values

# App names used by WhatsApp clients for Linux: WhatsApp Desktop (io.github.mimbrero,
# installed by the official package's script), ZapZap and WasIstLos.
WHATSAPP_APPS = ("whatsapp", "zapzap", "wasistlos")
WEB_ORIGIN = "web.whatsapp.com"  # browsers put the site in the notification body
EXPIRE_AFTER = 30 * 60.0

_MARKUP = re.compile(r"<[^>]*>")


@dataclass(frozen=True)
class Notification:
    app: str
    title: str
    body: str


def is_whatsapp(notification: Notification) -> bool:
    app = notification.app.lower()
    return any(name in app for name in WHATSAPP_APPS) or WEB_ORIGIN in notification.body


def message_text(body: str) -> str:
    """Notification body as plain text, without markup or the browser's origin line."""
    text = html.unescape(_MARKUP.sub("", body))
    lines = [line for line in text.splitlines() if line.strip() != WEB_ORIGIN]
    return "\n".join(lines).strip()


class NotificationSource(Source):
    name: ClassVar[str] = "notifications"
    interval: ClassVar[float] = 2.0

    def __init__(
        self, expire_after: float = EXPIRE_AFTER, clock: Callable[[], float] = time.monotonic
    ):
        self._expire_after = expire_after
        self._clock = clock
        self._lock = threading.Lock()
        self._latest: tuple[Notification, float] | None = None

    def push(self, notification: Notification) -> None:
        """Called by the monitor, from its own thread, for every notification."""
        if is_whatsapp(notification):
            with self._lock:
                self._latest = (notification, self._clock())

    def clear(self) -> None:
        with self._lock:
            self._latest = None

    def read(self) -> Values:
        with self._lock:
            latest = self._latest
        if latest is not None and self._clock() - latest[1] > self._expire_after:
            self.clear()
            latest = None
        # MESSAGE_BACKGROUND1/2 are 1 in every capture of the official app.
        values: Values = {tags.MESSAGE_BACKGROUND1: 1, tags.MESSAGE_BACKGROUND2: 1}
        if latest is None:
            return values | {
                tags.NOTIFICATION_SENDER: "",
                tags.NOTIFICATION_TEXT: "",
                tags.WHATSAPP_LOGO: 0,
            }
        notification = latest[0]
        text = tags.wrap_lines(message_text(notification.body), tags.MESSAGE_LINE)
        return values | {
            tags.NOTIFICATION_SENDER: notification.title,
            tags.NOTIFICATION_TEXT: text,
            tags.WHATSAPP_LOGO: 1,
        }
