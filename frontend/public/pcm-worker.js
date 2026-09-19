/**
 * High-Performance AudioWorkletProcessor
 * Runs on the browser's dedicated real-time audio thread.
 * Converts incoming Float32 PCM samples to 16-bit signed integer PCM (16kHz mono).
 * Emits raw buffers via zero-copy ArrayBuffer transfer list.
 */
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferSize = 1600; // 100ms chunks at 16kHz
    this.pcmBuffer = new Int16Array(this.bufferSize);
    this.bufferIndex = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;

    const channelData = input[0];
    const length = channelData.length;

    // Calculate instant RMS audio level for waveform visualization
    let sum = 0;
    for (let i = 0; i < length; i++) {
      const sample = channelData[i];
      sum += sample * sample;

      // Float32 to Int16 conversion with clipping prevention
      const s = Math.max(-1, Math.min(1, sample));
      this.pcmBuffer[this.bufferIndex++] = s < 0 ? s * 0x8000 : s * 0x7fff;

      // When chunk is filled, send directly over port
      if (this.bufferIndex >= this.bufferSize) {
        const chunkToSend = this.pcmBuffer.slice();
        this.port.postMessage(
          { type: "audio_data", buffer: chunkToSend.buffer },
          [chunkToSend.buffer] // Zero-copy transfer
        );
        this.bufferIndex = 0;
      }
    }

    const rms = Math.sqrt(sum / length);
    this.port.postMessage({ type: "level", level: Math.min(1.0, rms * 5) });

    return true;
  }
}

registerProcessor("pcm-processor", PCMProcessor);
