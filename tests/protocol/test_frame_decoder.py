from captures import official_app_frames

from minitela.protocol.frame import Frame, FrameDecoder

HANDSHAKE = Frame(0x0080)
BRIGHTNESS = Frame(0x0090, bytes.fromhex("80 0007 00000064"))


def decode(*chunks: bytes, **kwargs) -> list[Frame]:
    decoder = FrameDecoder(**kwargs)
    frames = []
    for chunk in chunks:
        frames += decoder.feed(chunk)
    return frames


def test_single_frame():
    assert decode(BRIGHTNESS.encode()) == [BRIGHTNESS]


def test_frame_with_crc_flag():
    assert decode(BRIGHTNESS.encode(crc=True)) == [BRIGHTNESS]


def test_merged_frames():
    assert decode(HANDSHAKE.encode() + BRIGHTNESS.encode()) == [HANDSHAKE, BRIGHTNESS]


def test_byte_by_byte():
    data = HANDSHAKE.encode() + BRIGHTNESS.encode()
    assert decode(*(data[i : i + 1] for i in range(len(data)))) == [HANDSHAKE, BRIGHTNESS]


def test_frame_returned_only_when_complete():
    decoder = FrameDecoder()
    data = BRIGHTNESS.encode()
    assert decoder.feed(data[:-1]) == []
    assert decoder.feed(data[-1:]) == [BRIGHTNESS]


def test_noise_between_frames():
    noise = b"\x00\xffxyz"
    assert decode(noise + HANDSHAKE.encode() + noise + BRIGHTNESS.encode() + noise) == [
        HANDSHAKE,
        BRIGHTNESS,
    ]


def test_false_start_marker_is_skipped():
    # "AH" followed by a length whose end marker is missing.
    false_start = b"AH\x00\x03\x00\x80\x00"
    assert decode(false_start + HANDSHAKE.encode()) == [HANDSHAKE]


def test_start_marker_split_across_reads():
    data = b"noise A" + b"H" + HANDSHAKE.encode()[2:]
    assert decode(data[:7], data[7:]) == [HANDSHAKE]


def test_length_too_short_is_skipped():
    assert decode(b"AH\x00\x01" + HANDSHAKE.encode()) == [HANDSHAKE]


def test_max_length_bounds_false_starts():
    false_start = b"AH\x10\x00"  # claims a 4 KiB body
    assert decode(false_start + HANDSHAKE.encode(), max_length=1024) == [HANDSHAKE]
    assert decode(false_start + HANDSHAKE.encode()) == []


def test_official_app_frames_as_one_stream():
    captured = official_app_frames()
    stream = b"".join(captured)
    frames = decode(*(stream[i : i + 7] for i in range(0, len(stream), 7)))
    assert len(frames) == len(captured)
    assert [frame.encode()[4:-4] for frame in frames] == [c[4:-4] for c in captured]
