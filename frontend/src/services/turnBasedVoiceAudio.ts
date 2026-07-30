export const TURN_BASED_STT_SAMPLE_RATE = 16_000
export const TURN_BASED_STT_AUDIO_FORMAT = 'wav'
export const TURN_BASED_STT_AUDIO_MIME_TYPE = 'audio/wav'

export function downmixAndResampleAudio(
  channels: readonly Float32Array[],
  sourceSampleRate: number,
  targetSampleRate: number = TURN_BASED_STT_SAMPLE_RATE,
): Float32Array {
  if (!channels.length || !Number.isFinite(sourceSampleRate) || sourceSampleRate <= 0) {
    return new Float32Array()
  }

  const frameCount = Math.min(...channels.map((channel) => channel.length))
  if (!frameCount) return new Float32Array()

  const targetFrameCount = Math.max(1, Math.round(frameCount * targetSampleRate / sourceSampleRate))
  const output = new Float32Array(targetFrameCount)
  const sourceStep = sourceSampleRate / targetSampleRate

  for (let index = 0; index < targetFrameCount; index += 1) {
    const position = Math.min(index * sourceStep, frameCount - 1)
    const leftIndex = Math.floor(position)
    const rightIndex = Math.min(leftIndex + 1, frameCount - 1)
    const fraction = position - leftIndex
    let mixedSample = 0

    for (const channel of channels) {
      mixedSample += channel[leftIndex] + (channel[rightIndex] - channel[leftIndex]) * fraction
    }
    output[index] = mixedSample / channels.length
  }

  return output
}

export function encodePcmWav(samples: Float32Array, sampleRate: number): ArrayBuffer {
  const bytesPerSample = 2
  const dataSize = samples.length * bytesPerSample
  const buffer = new ArrayBuffer(44 + dataSize)
  const view = new DataView(buffer)

  writeAscii(view, 0, 'RIFF')
  view.setUint32(4, 36 + dataSize, true)
  writeAscii(view, 8, 'WAVE')
  writeAscii(view, 12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * bytesPerSample, true)
  view.setUint16(32, bytesPerSample, true)
  view.setUint16(34, 16, true)
  writeAscii(view, 36, 'data')
  view.setUint32(40, dataSize, true)

  samples.forEach((sample, index) => {
    const clamped = Math.max(-1, Math.min(1, sample))
    view.setInt16(44 + index * bytesPerSample, Math.round(clamped * 0x7fff), true)
  })

  return buffer
}

export async function normalizeRecordedAudioToWav(recordedAudio: Blob): Promise<Blob> {
  const audioContext = new AudioContext()
  try {
    const decoded = await audioContext.decodeAudioData(await recordedAudio.arrayBuffer())
    const channels = Array.from(
      { length: decoded.numberOfChannels },
      (_, index) => decoded.getChannelData(index),
    )
    const samples = downmixAndResampleAudio(channels, decoded.sampleRate)
    if (!samples.length) {
      throw new Error('The recording did not contain decodable audio samples.')
    }

    return new Blob(
      [encodePcmWav(samples, TURN_BASED_STT_SAMPLE_RATE)],
      { type: TURN_BASED_STT_AUDIO_MIME_TYPE },
    )
  } finally {
    await audioContext.close()
  }
}

function writeAscii(view: DataView, offset: number, value: string): void {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index))
  }
}
