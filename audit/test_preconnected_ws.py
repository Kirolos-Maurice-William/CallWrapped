import asyncio
import aiohttp
import time
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from edge_tts.constants import WSS_URL, WSS_HEADERS, SEC_MS_GEC_VERSION
from edge_tts.drm import DRM
from edge_tts.communicate import (
    connect_id, _SSL_CTX, date_to_string, ssml_headers_plus_data, mkssml, TTSConfig
)

async def test_preconnected_ws():
    session = aiohttp.ClientSession(trust_env=True)
    url = f"{WSS_URL}&ConnectionId={connect_id()}&Sec-MS-GEC={DRM.generate_sec_ms_gec()}&Sec-MS-GEC-Version={SEC_MS_GEC_VERSION}"
    t0 = time.perf_counter()
    ws = await session.ws_connect(
        url,
        compress=15,
        headers=DRM.headers_with_muid(WSS_HEADERS),
        ssl=_SSL_CTX,
    )
    ws_connect_ms = (time.perf_counter() - t0) * 1000
    print(f"WebSocket pre-connected in {ws_connect_ms:.1f}ms")
    
    # Hold connection for 2 seconds (simulating offer waiting period)
    await asyncio.sleep(2.0)
    print(f"WebSocket still open after 2s: {not ws.closed}")
    
    # Now simulate confirmation: send speech.config and SSML immediately
    t_confirm = time.perf_counter()
    
    # Send config
    config_msg = (
        f"X-Timestamp:{date_to_string()}\r\n"
        "Content-Type:application/json; charset=utf-8\r\n"
        "Path:speech.config\r\n\r\n"
        '{"context":{"synthesis":{"audio":{"metadataoptions":{'
        '"sentenceBoundaryEnabled":"true","wordBoundaryEnabled":"false"'
        '},"outputFormat":"audio-24khz-48kbitrate-mono-mp3"}}}}\r\n'
    )
    await ws.send_str(config_msg)
    
    # Send SSML
    tc = TTSConfig("ar-EG-ShakirNeural", "-3%", "+0%", "+0Hz", "SentenceBoundary")
    text = "تصحيح سريع كارت الشاشة بيجي بـ 12 جيجا"
    ssml = mkssml(tc, text)
    await ws.send_str(ssml_headers_plus_data(connect_id(), date_to_string(), ssml))
    
    ttfb = 0
    async for msg in ws:
        if msg.type == aiohttp.WSMsgType.BINARY:
            if ttfb == 0:
                ttfb = (time.perf_counter() - t_confirm) * 1000
                print(f"🔥 First audio chunk received in: {ttfb:.1f}ms!")
                break
                
    await ws.close()
    await session.close()

if __name__ == "__main__":
    asyncio.run(test_preconnected_ws())
