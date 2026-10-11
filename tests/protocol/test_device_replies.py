"""Parse the replies recorded from the real device (tests/fixtures/device-replies.hex)."""

from captures import FIXTURES, read_capture

from minitela.protocol.commands import (
    RESULT_OK,
    Command,
    DownloadStatusResponse,
    HandshakeResponse,
    RequestDownloadResponse,
    ResultResponse,
    parse_response,
)
from minitela.protocol.frame import Frame, FrameDecoder
from minitela.protocol.registers import WriteAck, parse_register_values, parse_write_ack
from minitela.transport.fake import SimulatedScreen


def exchanges() -> list[tuple[Frame, Frame]]:
    """(request, reply) pairs from the recording."""
    decoder = FrameDecoder()
    frames = [
        (direction, frame)
        for _, direction, data in read_capture(FIXTURES / "device-replies.hex")
        for frame in decoder.feed(data)
    ]
    requests = [frame for direction, frame in frames if direction == ">"]
    replies = [frame for direction, frame in frames if direction == "<"]
    assert len(requests) == len(replies)
    return list(zip(requests, replies, strict=True))


def test_every_reply_answers_its_request():
    for request, reply in exchanges():
        assert reply.command == Command(request.command).response


def test_parsed_replies():
    replies = [reply for _, reply in exchanges()]
    assert parse_response(replies[0]) == HandshakeResponse(max_packet_length=1024)
    assert isinstance(parse_response(replies[1]), DownloadStatusResponse)
    software = parse_register_values(replies[2])[10]
    assert software.rstrip(b"\0") == b"1.10.19_build_2024.09.20_GIFTest"
    assert parse_register_values(replies[4]) == {2: 1, 7: 75}
    assert parse_write_ack(replies[5]) == WriteAck(0, ((7, 0),))
    assert parse_write_ack(replies[6]) == WriteAck(0, ((7, 0), (2, 0)))
    assert parse_write_ack(replies[7]) == WriteAck(0, ((1082, 0),))
    assert parse_register_values(replies[8])[1082].rstrip(b"\0") == b"100%"


def test_simulated_screen_replies_like_the_device():
    screen = SimulatedScreen()
    screen.numbers = {2: 1, 7: 75}
    for request, reply in exchanges():
        if request.command != Command.SET_REGISTER or request.payload[0] == 0xE0:
            continue  # the simulator knows no version strings
        assert screen(request) == [reply]


def test_upload_replies():
    """The device's answers while receiving a texture (tests/fixtures/device-upload.hex)."""
    decoder = FrameDecoder()
    replies = [
        frame
        for _, direction, data in read_capture(FIXTURES / "device-upload.hex")
        if direction == "<"
        for frame in decoder.feed(data)
    ]
    parsed = [parse_response(frame) for frame in replies]
    assert parsed[0] == HandshakeResponse(max_packet_length=1024)
    assert parsed[1] == RequestDownloadResponse(max_page_size=1024, result=RESULT_OK)
    assert all(r == ResultResponse(Command.DOWNLOAD_DATA, RESULT_OK) for r in parsed[2:-1])
    assert parsed[-1] == ResultResponse(Command.DOWNLOAD_COMPLETE, RESULT_OK)
