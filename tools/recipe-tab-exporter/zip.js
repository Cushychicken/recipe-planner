/* ZIP STORE format, no dependencies or network requests. */
(function(root) {
  'use strict';
  function crc32(bytes) {
    let crc = 0xffffffff;
    for (const byte of bytes) {
      crc ^= byte;
      for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
    }
    return (crc ^ 0xffffffff) >>> 0;
  }
  function header(size, values) {
    const bytes = new Uint8Array(size), view = new DataView(bytes.buffer);
    for (const [offset, width, value] of values) {
      if (width === 2) view.setUint16(offset, value, true);
      else view.setUint32(offset, value, true);
    }
    return bytes;
  }
  function makeZip(files) {
    const encoder = new TextEncoder(), local = [], central = [];
    let offset = 0, centralSize = 0;
    if (files.length > 65535) throw Error('Too many files for a ZIP archive.');
    for (const file of files) {
      const name = encoder.encode(file.name);
      const data = typeof file.content === 'string' ? encoder.encode(file.content) : file.content;
      if (data.length > 0xffffffff || offset > 0xffffffff) throw Error('Archive exceeds ZIP size limits.');
      const crc = crc32(data);
      const entry = header(30, [[0,4,0x04034b50],[4,2,20],[6,2,0x800],[12,2,33],
        [14,4,crc],[18,4,data.length],[22,4,data.length],[26,2,name.length]]);
      const directory = header(46, [[0,4,0x02014b50],[4,2,20],[6,2,20],[8,2,0x800],[14,2,33],
        [16,4,crc],[20,4,data.length],[24,4,data.length],[28,2,name.length],[42,4,offset]]);
      local.push(entry,name,data);
      central.push(directory,name);
      offset += entry.length + name.length + data.length;
      centralSize += directory.length + name.length;
    }
    const end = header(22, [[0,4,0x06054b50],[8,2,files.length],[10,2,files.length],
      [12,4,centralSize],[16,4,offset]]);
    return new Blob([...local,...central,end], {type:'application/zip'});
  }
  const api = {crc32, makeZip};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.RecipeZip = api;
})(globalThis);
