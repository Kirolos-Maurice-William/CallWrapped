/**
 * High-Performance AudioStreamer
 * 1. Captures local microphone using off-main-thread AudioWorklet (16kHz mono).
 * 2. Transmits raw PCM16 binary chunks over WebSocket.
 * 3. Receives peer audio chunks over the same WebSocket and plays them through browser speakers.
 */
export class AudioStreamer {
  private mediaStream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private peerAudioDestination: MediaStreamAudioDestinationNode | null = null;
  private peerAudioElement: HTMLAudioElement | null = null;
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

    // 2. Request user microphone with native hardware/browser echo cancellation
    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: 16000,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        // @ts-ignore
        googEchoCancellation: true,
        googAutoGainControl: true,
        googNoiseSuppression: true,
        googHighpassFilter: true,
      },
    });

    // 3. Audio Context
    this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)({
      sampleRate: 16000,
    });

    // 4. Chrome Native AEC Integration:
    // Route peer audio output to an HTML <audio> element via MediaStreamDestination.
    // This allows Chromium's WebRTC AEC3 engine to recognize the sound and cancel it from the mic!
    try {
      this.peerAudioDestination = this.audioContext.createMediaStreamDestination();
      this.peerAudioElement = document.createElement("audio");
      this.peerAudioElement.srcObject = this.peerAudioDestination.stream;
      this.peerAudioElement.autoplay = true;
      // @ts-ignore
      this.peerAudioElement.playsInline = true;
      this.peerAudioElement.play().catch(() => {});
    } catch (e) {
      console.warn("Could not create MediaStreamDestination for AEC:", e);
    }

    // 5. Play incoming peer audio from WebSocket
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

    // Fallback: ScriptProcessorNode (1024 samples = 64ms for low latency)
    this.fallbackProcessor = this.audioContext.createScriptProcessor(1024, 1, 1);
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
    if (this.peerAudioDestination) {
      sourceNode.connect(this.peerAudioDestination);
    } else {
      sourceNode.connect(this.audioContext.destination);
    }

    // Ultra-low latency scheduling with anti-drift catch-up
    const currentTime = this.audioContext.currentTime;
    // Catch-up: if buffer lag drifted more than 50ms, immediately resync to real-time!
    if (this.nextPlaybackTime < currentTime || this.nextPlaybackTime > currentTime + 0.05) {
      this.nextPlaybackTime = currentTime + 0.01; // 10ms minimal jitter buffer
    }
    sourceNode.start(this.nextPlaybackTime);
    this.nextPlaybackTime += audioBuffer.duration;
  }

  stop(): void {
    this.isStreaming = false;
    this.nextPlaybackTime = 0;
    if (this.peerAudioElement) {
      try {
        this.peerAudioElement.pause();
        this.peerAudioElement.srcObject = null;
        this.peerAudioElement.remove();
      } catch (e) {}
      this.peerAudioElement = null;
    }
    if (this.peerAudioDestination) {
      try { this.peerAudioDestination.disconnect(); } catch (e) {}
      this.peerAudioDestination = null;
    }
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
