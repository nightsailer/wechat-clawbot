"""SILK to WAV transcoding (optional dependency: graiax-silkcoder)."""

from __future__ import annotations

import struct

from wechat_clawbot.util.logger import logger

_SILK_SAMPLE_RATE = 24_000


def _pcm_bytes_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw pcm_s16le bytes in a WAV container (mono, 16-bit signed LE)."""
    pcm_len = len(pcm)
    total_size = 44 + pcm_len
    header = struct.pack(
        "<4sI4s"  # RIFF header
        "4sIHHIIHH"  # fmt chunk
        "4sI",  # data chunk header
        b"RIFF",
        total_size - 8,
        b"WAVE",
        b"fmt ",
        16,  # fmt chunk size
        1,  # PCM format
        1,  # mono
        sample_rate,
        sample_rate * 2,  # byte rate
        2,  # block align
        16,  # bits per sample
        b"data",
        pcm_len,
    )
    return header + pcm


async def silk_to_wav(silk_buf: bytes) -> bytes | None:
    """Try to transcode a SILK audio buffer to WAV.

    Returns WAV bytes on success, or ``None`` if the silk decoder is unavailable.
    """
    try:
        from graiax.silkcoder import async_decode

        logger.debug(f"silkToWav: decoding {len(silk_buf)} bytes of SILK")
        pcm = await async_decode(silk_buf, to_wav=False, sample_rate=_SILK_SAMPLE_RATE)
        wav = _pcm_bytes_to_wav(pcm, _SILK_SAMPLE_RATE)
        logger.debug(f"silkToWav: WAV size={len(wav)}")
        return wav
    except ImportError:
        logger.warning("silkToWav: graiax-silkcoder not installed, returning raw silk")
        return None
    except Exception as e:
        logger.warning(f"silkToWav: transcode failed, will use raw silk err={e}")
        return None
