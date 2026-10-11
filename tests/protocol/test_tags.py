from datetime import datetime

import pytest
from captures import official_app_frames

from minitela.protocol import tags
from minitela.protocol.frame import FrameDecoder
from minitela.protocol.tags import REGISTERS, Kind


def test_registry_has_unique_ids():
    ids = [register.id for register in REGISTERS.values()]
    assert len(ids) == len(set(ids))


def test_registry_lookup_by_name():
    assert REGISTERS["brightness"] is tags.BRIGHTNESS
    assert REGISTERS["date_hour"].id == 2006


def test_text_registers_have_a_limit():
    for register in REGISTERS.values():
        assert (register.kind is Kind.TEXT) == (register.max_length is not None), register


def test_captured_registers_are_known():
    # The official app also clears 1142 and 1143, which the factory layout does not have.
    not_in_layout = {1142, 1143}
    known = {register.id for register in REGISTERS.values()}
    for captured in official_app_frames():
        (frame,) = FrameDecoder().feed(captured)
        register = int.from_bytes(frame.payload[1:3])
        assert register in known | not_in_layout


def test_pages():
    assert tags.Page.WHATSAPP == 1
    assert tags.Page.GIF1 == 5


@pytest.mark.parametrize(("number", "name"), [(1, "whatsapp"), (5, "gif1"), (8, "unknown")])
def test_page_name(number, name):
    assert tags.page_name(number) == name


def test_battery_text():
    assert tags.battery_text(100) == "100%"


@pytest.mark.parametrize(
    ("percent", "icon"), [(-5, 0), (0, 0), (24, 0), (25, 1), (50, 2), (99, 3), (100, 3), (120, 3)]
)
def test_battery_icon(percent, icon):
    assert tags.battery_icon(percent) == icon


@pytest.mark.parametrize(
    ("name", "label"),
    [
        (None, "Desconectado"),
        ("", "Desconectado"),
        ("casa", "casa"),
        ("rede-casa", "rede-casa"),
        ("brisa-5123339", "brisa-512..."),
    ],
)
def test_connection_label(name, label):
    assert tags.connection_label(name) == label


def test_date_hour():
    assert tags.date_hour(datetime(2026, 10, 11, 2, 21, 59)) == "11/10 02:21"


def test_device_clock():
    moment = datetime(2026, 10, 11, 14, 5, 9)
    assert tags.clock_date(moment) == 0x20261011
    assert tags.clock_time(moment) == 0x140509


@pytest.mark.parametrize(
    ("text", "wrapped"),
    [
        ("", ""),
        ("curto", "curto"),
        (
            "Isso e apenas um teste, por favor respeite o teste.",
            "Isso e apenas um\nteste, por favor\nrespeite o\nteste.",
        ),
        ("linha 1\nlinha 2", "linha 1\nlinha 2"),
        ("antes\n\ndepois", "antes\n\ndepois"),
        ("palavragrandedemaisparaumalinha", "palavragrandedem\naisparaumalinha"),
        ("guarda-chuva amarelo", "guarda-chuva\namarelo"),
    ],
)
def test_wrap_lines(text, wrapped):
    assert tags.wrap_lines(text, 16) == wrapped
