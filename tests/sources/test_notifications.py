import threading

import pytest

from minitela.protocol import tags
from minitela.sources.notifications import (
    Notification,
    NotificationSource,
    is_whatsapp,
    message_text,
)

EMPTY = {
    tags.NOTIFICATION_SENDER: "",
    tags.NOTIFICATION_TEXT: "",
    tags.WHATSAPP_LOGO: 0,
    tags.MESSAGE_BACKGROUND1: 1,
    tags.MESSAGE_BACKGROUND2: 1,
}


@pytest.mark.parametrize(
    ("app", "body", "expected"),
    [
        ("WhatsApp", "Oi", True),
        ("ZapZap", "Oi", True),
        ("WasIstLos", "Oi", True),
        ("Chromium", '<a href="https://web.whatsapp.com/">web.whatsapp.com</a>\n\nOi', True),
        ("Firefox", "web.whatsapp.com\nOi", True),
        ("Chromium", "github.com\n\nNew issue", False),
        ("Telegram Desktop", "Oi", False),
        ("notify-send", "Backup finished", False),
    ],
)
def test_is_whatsapp(app, body, expected):
    assert is_whatsapp(Notification(app, "Maria", body)) is expected


@pytest.mark.parametrize(
    ("body", "text"),
    [
        ("Oi, tudo bem?", "Oi, tudo bem?"),
        (
            '<a href="https://web.whatsapp.com/">web.whatsapp.com</a>\n\nOi &amp; tchau',
            "Oi & tchau",
        ),
        ("<b>Foto</b>", "Foto"),
        ("  linha 1\nlinha 2  ", "linha 1\nlinha 2"),
    ],
)
def test_message_text(body, text):
    assert message_text(body) == text


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def source(clock):
    return NotificationSource(expire_after=60, clock=clock)


def test_no_notification(source):
    assert source.read() == EMPTY


def test_latest_whatsapp_notification(source):
    source.push(Notification("WhatsApp", "Maria", "Primeira"))
    source.push(Notification("WhatsApp", "João", "Chegou a encomenda que você pediu ontem"))
    source.push(Notification("Thunderbird", "Chefe", "Reunião"))  # not from WhatsApp
    assert source.read() == EMPTY | {
        tags.NOTIFICATION_SENDER: "João",
        tags.NOTIFICATION_TEXT: "Chegou a\nencomenda que\nvocê pediu ontem",
        tags.WHATSAPP_LOGO: 1,
    }


def test_notification_expires(source, clock):
    source.push(Notification("WhatsApp", "Maria", "Oi"))
    clock.now += 60
    assert source.read()[tags.WHATSAPP_LOGO] == 1
    clock.now += 1
    assert source.read() == EMPTY


def test_clear(source):
    source.push(Notification("WhatsApp", "Maria", "Oi"))
    source.clear()
    assert source.read() == EMPTY


def test_push_from_another_thread(source):
    thread = threading.Thread(target=source.push, args=(Notification("WhatsApp", "Maria", "Oi"),))
    thread.start()
    thread.join()
    assert source.read()[tags.NOTIFICATION_SENDER] == "Maria"
