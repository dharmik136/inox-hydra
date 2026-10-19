/**
 * An unpacked LinkedIn archive, packed again in the browser.
 *
 * Safari unpacks a downloaded ZIP into a folder by default and removes the
 * ZIP. When the creator chooses that folder, its CSV files are put back into
 * a ZIP here, stored rather than compressed, so the studio reads it exactly
 * as it reads LinkedIn's own file, with the same limits. Nothing leaves the
 * machine: the result goes to the studio on 127.0.0.1 like any chosen file.
 */

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(data: Uint8Array): number {
  let c = 0xffffffff;
  for (let i = 0; i < data.length; i++) c = CRC_TABLE[(c ^ data[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

/** The file's path inside the chosen folder, without the folder itself. */
function inside(file: File): string {
  const path = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
  const parts = path.split("/");
  return parts.length > 1 ? parts.slice(1).join("/") : path;
}

/** The chosen folder's own name, which is LinkedIn's export name without ".zip". */
export function folderName(files: File[]): string {
  const path = (files[0] as (File & { webkitRelativePath?: string }) | undefined)?.webkitRelativePath ?? "";
  return path.split("/")[0] || "archive";
}

/** A ZIP of the folder's CSV files, as one file the studio can be sent. */
export async function zipFolder(files: File[]): Promise<File> {
  const csvs = files.filter((f) => f.name.toLowerCase().endsWith(".csv"));
  const encoder = new TextEncoder();
  const parts: BlobPart[] = [];
  const central: BlobPart[] = [];
  let offset = 0;
  let centralSize = 0;
  for (const file of csvs) {
    const name = encoder.encode(inside(file));
    const data = new Uint8Array(await file.arrayBuffer());
    const crc = crc32(data);
    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true);
    local.setUint16(4, 20, true);
    local.setUint16(6, 0x0800, true); // the name is UTF-8
    local.setUint16(12, 0x21, true); // 1 January 1980, the earliest date a ZIP can say
    local.setUint32(14, crc, true);
    local.setUint32(18, data.length, true);
    local.setUint32(22, data.length, true);
    local.setUint16(26, name.length, true);
    parts.push(local.buffer, name, data);
    const entry = new DataView(new ArrayBuffer(46));
    entry.setUint32(0, 0x02014b50, true);
    entry.setUint16(4, 20, true);
    entry.setUint16(6, 20, true);
    entry.setUint16(8, 0x0800, true);
    entry.setUint16(14, 0x21, true);
    entry.setUint32(16, crc, true);
    entry.setUint32(20, data.length, true);
    entry.setUint32(24, data.length, true);
    entry.setUint16(28, name.length, true);
    entry.setUint32(42, offset, true);
    central.push(entry.buffer, name);
    offset += 30 + name.length + data.length;
    centralSize += 46 + name.length;
  }
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true);
  end.setUint16(8, csvs.length, true);
  end.setUint16(10, csvs.length, true);
  end.setUint32(12, centralSize, true);
  end.setUint32(16, offset, true);
  return new File([...parts, ...central, end.buffer], folderName(files), { type: "application/zip" });
}
