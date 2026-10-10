// Binary arrays of the bundle: little-endian int16 in hundredths of a kelvin, MISSING for no value.

export const MISSING = -32768;
export const SCALE = 100;

/** Decode int16 values to floats, with NaN for missing entries. */
export function decodeInt16(
  buffer: ArrayBuffer,
  offset = 0,
  length?: number,
  scale = SCALE,
  missing = MISSING
): Float32Array {
  const view = new DataView(buffer);
  const n = length ?? (buffer.byteLength - offset) / 2;
  const out = new Float32Array(n);
  for (let k = 0; k < n; k++) {
    const raw = view.getInt16(offset + 2 * k, true);
    out[k] = raw === missing ? Number.NaN : raw / scale;
  }
  return out;
}

/** A scene file holds the anomaly layer followed by the absolute LST layer, each `nZones` long. */
export function decodeScene(
  buffer: ArrayBuffer,
  nZones: number
): { anomaly: Float32Array; lst: Float32Array } {
  if (buffer.byteLength !== 4 * nZones) {
    throw new Error(`scene file has ${buffer.byteLength} bytes, expected ${4 * nZones}`);
  }
  return { anomaly: decodeInt16(buffer, 0, nZones), lst: decodeInt16(buffer, 2 * nZones, nZones) };
}

/** Chunk holding zone `index` and the zone's position inside it. */
export function chunkOf(index: number, chunkSize: number): { chunk: number; offset: number } {
  return { chunk: Math.floor(index / chunkSize), offset: index % chunkSize };
}

/** Time series of one zone from a decoded chunk laid out zone-major (`chunkLength x nScenes`). */
export function seriesFromChunk(
  chunk: Float32Array,
  offset: number,
  nScenes: number
): Float32Array {
  return chunk.subarray(offset * nScenes, (offset + 1) * nScenes);
}
