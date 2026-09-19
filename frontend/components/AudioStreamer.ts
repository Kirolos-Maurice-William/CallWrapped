/**
 * High-Performance AudioStreamer
 * 1. Captures local microphone using off-main-thread AudioWorklet (16kHz mono).
 * 2. Transmits raw PCM16 binary chunks over WebSocket.
 * 3. Receives peer audio chunks over the same WebSocket and plays them through browser speakers.
 */
export class AudioStreamer {
  private mediaStream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private fallbackProcessor: ScriptProcessorNode | null = null;
  private socket: WebSocket | null = null;
  public isStreaming = false;

  private serverWsUrl: string;

  constructor(
    private callId: string,
    private speakerId: string,
    serverWsUrl?: string
  ) {
    if (serverWsUrl) {
      this.serverWsUrl = serverWsUrl;
    } else if (typeof window !== "undefined") {
      const isHttps = window.location.protocol === "https:";
      const wsProtocol = isHttps ? "wss:" : "ws:";
      if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
        this.serverWsUrl = `${wsProtocol}//${window.location.hostname}:8000`;
      } else {
        this.serverWsUrl = `${wsProtocol}//${window.location.host}`;
      }
    } else {
      this.serverWsUrl = "ws://localhost:8000";
    }
  }

  async start(onAudioData?: (level: number) => void): Promise<void> {
    if (this.isStreaming) return;

    // 1. Establish binary WebSocket connection
    const wsUrl = `${this.serverWsUrl}/ws/audio/${this.callId}/${this.speakerId}`;
    this.socket = new WebSocket(wsUrl);
    this.socket.binaryType = "arraybuffer";

    await new Promise<void>((resolve, reject) => {
      if (!this.socket) return reject("No socket instance");
      this.socket.onopen = () => resolve();
      this.socket.onerror = (err) => reject(err);
    });

    // 2. Request user microphone (16kHz mono)
    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: 16000,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    // 3. Audio Context
    this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)({
      sampleRate: 16000,
    });

    // 4. Play incoming peer audio from WebSocket
    this.socket.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer && this.audioContext) {
        this.playPeerAudioChunk(event.data);
      }
    };

    const source = this.audioContext.createMediaStreamSource(this.mediaStream);

    // 5. Prefer AudioWorklet for off-main-thread zero-jank processing
    if (this.audioContext.audioWorklet) {
      try {
        await this.audioContext.audioWorklet.addModule("/pcm-worker.js");
        this.workletNode = new AudioWorkletNode(this.audioContext, "pcm-processor");

        this.workletNode.port.onmessage = (event) => {
          const { type, buffer, level } = event.data;
          if (type === "level" && onAudioData) {
            onAudioData(level);
          } else if (type === "audio_data" && this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(buffer);
          }
        };

        source.connect(this.workletNode);
        // Route through zero-gain mute node: guarantees worklet processing without playing mic into local speakers
        const muteNode = this.audioContext.createGain();
        muteNode.gain.value = 0;
        this.workletNode.connect(muteNode);
        muteNode.connect(this.audioContext.destination);
        this.isStreaming = true;
        return;
      } catch (workletError) {
        console.warn("AudioWorklet failed, using fallback ScriptProcessorNode:", workletError);
      }
    }

    // Fallback: ScriptProcessorNode
    this.fallbackProcessor = this.audioContext.createScriptProcessor(2048, 1, 1);
    this.fallbackProcessor.onaudioprocess = (e) => {
      if (!this.isStreaming || !this.socket || this.socket.readyState !== WebSocket.OPEN) return;

      const inputData = e.inputBuffer.getChannelData(0);
      let sum = 0;
      for (let i = 0; i < inputData.length; i++) {
        sum += inputData[i] * inputData[i];
      }
      if (onAudioData) onAudioData(Math.min(1.0, Math.sqrt(sum / inputData.length) * 5));

      const pcm16 = new Int16Array(inputData.length);
      for (let i = 0; i < inputData.length; i++) {
        const s = Math.max(-1, Math.min(1, inputData[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      this.socket.send(pcm16.buffer);
    };

    source.connect(this.fallbackProcessor);
    const fallbackMute = this.audioContext.createGain();
    fallbackMute.gain.value = 0;
    this.fallbackProcessor.connect(fallbackMute);
    fallbackMute.connect(this.audioContext.destination);
    this.isStreaming = true;
  }

  private nextPlaybackTime: number = 0;

  private playPeerAudioChunk(buffer: ArrayBuffer): void {
    if (!this.audioContext) return;
    if (this.audioContext.state === "suspended") {
      this.audioContext.resume();
    }
    const pcm16 = new Int16Array(buffer);
    if (pcm16.length === 0) return;

    const audioBuffer = this.audioContext.createBuffer(1, pcm16.length, 16000);
    const channelData = audioBuffer.getChannelData(0);

    for (let i = 0; i < pcm16.length; i++) {
      channelData[i] = pcm16[i] / 32768.0;
    }

    const sourceNode = this.audioContext.createBufferSource();
    sourceNode.buffer = audioBuffer;
    sourceNode.connect(this.audioContext.destination);

    // Smooth sample-accurate scheduling to eliminate crackling and overlapping echo
    const currentTime = this.audioContext.currentTime;
    if (this.nextPlaybackTime < currentTime) {
      this.nextPlaybackTime = currentTime + 0.02; // 20ms jitter buffer
    }
    sourceNode.start(this.nextPlaybackTime);
    this.nextPlaybackTime += audioBuffer.duration;
  }

  stop(): void {
    this.isStreaming = false;
    this.nextPlaybackTime = 0;
    if (this.workletNode) {
      try { this.workletNode.disconnect(); } catch (e) {}
      this.workletNode = null;
    }
    if (this.fallbackProcessor) {
      try { this.fallbackProcessor.disconnect(); } catch (e) {}
      this.fallbackProcessor = null;
    }
    if (this.mediaStream) {
      try {
        this.mediaStream.getTracks().forEach((track) => track.stop());
      } catch (e) {}
      this.mediaStream = null;
    }
    if (this.audioContext) {
      try { this.audioContext.close(); } catch (e) {}
      this.audioContext = null;
    }
    if (this.socket) {
      try { this.socket.close(); } catch (e) {}
      this.socket = null;
    }
  }
}
