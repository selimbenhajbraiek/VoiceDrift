// Recordings and uploads become 16 kHz mono WAV in the browser: the format the backend's models use, whatever
// the browser's own recorder would produce. Same approach as the phone page (backend/dashboard/static/phone.js).

export const RATE = 16000;

// Collects raw samples off the audio thread in blocks of 4096
const WORKLET = `registerProcessor("vd-capture", class extends AudioWorkletProcessor {
  constructor() { super(); this.buf = new Float32Array(4096); this.n = 0; }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) for (let i = 0; i < ch.length; i++) {
      this.buf[this.n++] = ch[i];
      if (this.n === this.buf.length) { this.port.postMessage(this.buf); this.buf = new Float32Array(4096); this.n = 0; }
    }
    return true;
  }
});`;

export interface Capture {
  /** Stop the microphone and return the recording as WAV. */
  stop: () => Promise<{ blob: Blob; seconds: number }>;
  /** Abandon the recording. */
  cancel: () => void;
}

/** Start recording; `onLevel` gets the loudness (0..1) of each block of samples. */
export async function startCapture(onLevel: (level: number) => void): Promise<Capture> {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error("This browser can't record here. Upload a recording instead.");
  const ctx = new AudioContext(); // created during the click, so the browser lets it start
  // Don't wait for resume(): without a real user gesture it never settles, and recording works once the mic is open
  ctx.resume().catch(() => {});
  const chunks: Float32Array[] = [];
  let frames = 0;
  let stream: MediaStream | undefined;
  let node: AudioNode | undefined;
  let source: MediaStreamAudioSourceNode | undefined;

  const take = (block: Float32Array) => {
    chunks.push(block);
    frames += block.length;
    let sum = 0;
    for (let i = 0; i < block.length; i++) sum += block[i] * block[i];
    const db = 20 * Math.log10(Math.sqrt(sum / block.length) + 1e-6); // -60 dB (silence) .. 0 dB (full scale)
    onLevel(Math.max(0, Math.min(1, (db + 60) / 60)));
  };
  const release = () => {
    stream?.getTracks().forEach((t) => t.stop());
    source?.disconnect();
    node?.disconnect();
    ctx.close().catch(() => {});
  };

  try {
    // Raw microphone: noise suppression and automatic gain would change the voice measures
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
    ctx.resume().catch(() => {}); // a page that is capturing the microphone may always run audio
    source = ctx.createMediaStreamSource(stream);
    if (ctx.audioWorklet && typeof AudioWorkletNode !== "undefined") {
      const url = URL.createObjectURL(new Blob([WORKLET], { type: "text/javascript" }));
      await ctx.audioWorklet.addModule(url);
      URL.revokeObjectURL(url);
      const worklet = new AudioWorkletNode(ctx, "vd-capture", { channelCount: 1, channelCountMode: "explicit" });
      worklet.port.onmessage = (e) => take(e.data as Float32Array);
      node = worklet;
    } else {
      const processor = ctx.createScriptProcessor(4096, 1, 1);
      processor.onaudioprocess = (e) => take(new Float32Array(e.inputBuffer.getChannelData(0)));
      node = processor;
    }
    const mute = ctx.createGain();
    mute.gain.value = 0; // the node must reach the speakers to run, but silently
    source.connect(node);
    node.connect(mute);
    mute.connect(ctx.destination);
  } catch (e) {
    release();
    throw new Error((e as DOMException)?.name === "NotAllowedError"
      ? "The microphone is blocked. Allow it for this page in the browser's settings, or upload a recording."
      : "Couldn't start the microphone. Upload a recording instead.");
  }

  return {
    stop: async () => {
      const rate = ctx.sampleRate;
      release();
      const samples = new Float32Array(frames);
      let at = 0;
      for (const block of chunks) {
        samples.set(block, at);
        at += block.length;
      }
      const out = await resample(samples, rate);
      return { blob: wav(out.samples, out.rate), seconds: frames / rate };
    },
    cancel: release,
  };
}

/** An uploaded file as 16 kHz WAV (decoded here, so phone voice memos and M4A work); the original if this browser can't. */
export async function fileToWav(file: File): Promise<{ blob: Blob; seconds: number | null }> {
  try {
    const ctx = new AudioContext();
    const decoded = await ctx.decodeAudioData(await file.arrayBuffer());
    ctx.close().catch(() => {});
    const out = await resample(mixdown(decoded), decoded.sampleRate);
    return { blob: wav(out.samples, out.rate), seconds: decoded.duration };
  } catch {
    return { blob: file, seconds: null }; // let the backend try
  }
}

// Resample to 16 kHz with the browser's own resampler; keep the original rate if it can't
async function resample(samples: Float32Array, rate: number) {
  if (rate === RATE) return { samples, rate };
  try {
    const off = new OfflineAudioContext(1, Math.ceil((samples.length * RATE) / rate), RATE);
    const buffer = off.createBuffer(1, samples.length, rate);
    buffer.getChannelData(0).set(samples);
    const src = off.createBufferSource();
    src.buffer = buffer;
    src.connect(off.destination);
    src.start();
    return { samples: (await off.startRendering()).getChannelData(0), rate: RATE };
  } catch {
    return { samples, rate };
  }
}

function mixdown(buffer: AudioBuffer) {
  const out = new Float32Array(buffer.length);
  for (let c = 0; c < buffer.numberOfChannels; c++) {
    const ch = buffer.getChannelData(c);
    for (let i = 0; i < out.length; i++) out[i] += ch[i] / buffer.numberOfChannels;
  }
  return out;
}

// 16-bit PCM mono WAV
function wav(samples: Float32Array, rate: number) {
  const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
  const text = (at: number, s: string) => { for (let i = 0; i < s.length; i++) view.setUint8(at + i, s.charCodeAt(i)); };
  text(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); text(8, "WAVE");
  text(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  text(36, "data"); view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([view], { type: "audio/wav" });
}
