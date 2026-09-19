import logging
from typing import Tuple, Any
from discord.opus import OpusError
from discord.ext.voice_recv.opus import PacketDecoder
import davey

logger = logging.getLogger("DAVEAdapter")

_original_decode_packet = PacketDecoder._decode_packet


def _patched_decode_packet(self: PacketDecoder, packet: Any) -> Tuple[Any, bytes]:
    assert self._decoder is not None
    SILENCE_FRAME = b"\x00" * 3840  # 20ms at 48kHz stereo

    def try_dave_decrypt(data_bytes: bytes) -> bytes:
        if not data_bytes:
            return data_bytes
        try:
            vc = getattr(self.sink, "voice_client", None)
            if not vc or not getattr(vc, "_connection", None):
                return data_bytes

            dave_session = getattr(vc._connection, "dave_session", None)
            proto_version = getattr(vc._connection, "dave_protocol_version", 0)

            # If DAVE is enabled on this channel
            if dave_session and proto_version > 0:
                user_id = self._cached_id or getattr(vc, "_ssrc_to_id", {}).get(self.ssrc)
                if not user_id and getattr(vc, "channel", None):
                    humans = [m.id for m in vc.channel.members if not m.bot]
                    if len(humans) == 1:
                        user_id = humans[0]

                if user_id:
                    decrypted = dave_session.decrypt(user_id, davey.MediaType.audio, data_bytes)
                    return decrypted
        except Exception as e:
            logger.debug(f"[DAVE Decrypt] Notice: {e}")
        return data_bytes

    if packet:
        payload = try_dave_decrypt(packet.decrypted_data)
        try:
            pcm = self._decoder.decode(payload, fec=False)
            return packet, pcm
        except OpusError as e:
            logger.debug(f"[DAVE] Corrupted Opus packet after decrypt attempt: {e}")
            return packet, SILENCE_FRAME

    next_packet = self._buffer.peek_next()
    if next_packet is not None:
        nextdata = try_dave_decrypt(next_packet.decrypted_data)
        try:
            pcm = self._decoder.decode(nextdata, fec=True)
        except OpusError:
            pcm = SILENCE_FRAME
    else:
        try:
            pcm = self._decoder.decode(None, fec=False)
        except OpusError:
            pcm = SILENCE_FRAME

    return packet, pcm


def install_dave_adapter():
    """Hooks DAVE E2EE audio decryption into discord-ext-voice-recv."""
    PacketDecoder._decode_packet = _patched_decode_packet
    logger.info("🛡️ [DAVE Adapter] Successfully installed DAVE E2EE decryption into discord-ext-voice-recv.")
