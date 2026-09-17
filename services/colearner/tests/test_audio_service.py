from src.services.audio_service import detect_audio_container


def test_detects_riff_wav():
    assert detect_audio_container(b"RIFF\x00\x00\x00\x00WAVEfmt ") == (".wav", "audio/wav")


def test_detects_m4a_mp4_container():
    # A real M4A/MP4 file's box layout: 4-byte size, then b"ftyp" at
    # offset 4 - this is exactly what expo-audio's HIGH_QUALITY recording
    # preset produces (see audio_service.py's detect_audio_container
    # docstring).
    assert detect_audio_container(b"\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00") == (".m4a", "audio/mp4")


def test_detects_ogg():
    assert detect_audio_container(b"OggS\x00\x02\x00\x00") == (".ogg", "audio/ogg")


def test_falls_back_to_webm_for_unrecognized_bytes():
    assert detect_audio_container(b"\x1a\x45\xdf\xa3\x00\x00\x00\x00") == (".webm", "audio/webm")
