"""WAVを再変換せず、RIFFチャンクと音声フレームの境界を検査する"""

import struct


def validate_wav(wav: bytes) -> None:
    """必須チャンクの欠落、空の音声、長さの不整合をValueErrorで通知"""
    if len(wav) < 12 or wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        raise ValueError("Missing RIFF/WAVE header")
    if int.from_bytes(wav[4:8], "little") + 8 != len(wav):
        raise ValueError("RIFF length does not match response length")

    offset = 12
    block_align = None
    data_found = False
    while offset < len(wav):
        if offset + 8 > len(wav):
            raise ValueError("Truncated WAV chunk header")
        chunk_id = wav[offset : offset + 4]
        size = int.from_bytes(wav[offset + 4 : offset + 8], "little")
        start = offset + 8
        end = start + size
        if end > len(wav):
            raise ValueError("Truncated WAV chunk data")
        if chunk_id == b"fmt ":
            if block_align is not None or size < 16:
                raise ValueError("Invalid WAV format chunk")
            tag, channels, rate, byte_rate, block_align, bits = struct.unpack_from(
                "<HHIIHH", wav, start
            )
            if not all((tag, channels, rate, byte_rate, block_align, bits)):
                raise ValueError("Invalid WAV format parameters")
            # PCM・浮動小数点・拡張形式では、1フレームの長さと転送量も見る
            if tag in (1, 3, 0xFFFE) and (
                block_align != channels * ((bits + 7) // 8) or byte_rate != rate * block_align
            ):
                raise ValueError("Inconsistent WAV frame size")
        elif chunk_id == b"data":
            if block_align is None:
                raise ValueError("WAV data precedes the format chunk")
            if not size or size % block_align:
                raise ValueError("Empty or incomplete WAV audio frames")
            data_found = True
        # 補助チャンクを保持し、奇数長のパディングを飛ばす。末尾の省略は許容
        offset = end if end == len(wav) else end + (size % 2)

    if block_align is None or not data_found:
        raise ValueError("Missing WAV format or audio data chunk")
