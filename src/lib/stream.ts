/** Splits a stream of text chunks into complete lines, holding back a trailing partial line. */
export function createLineParser(onLine: (line: string) => void) {
  let buffer = "";
  return {
    push(chunk: string) {
      buffer += chunk;
      let newline = buffer.indexOf("\n");
      while (newline !== -1) {
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        if (line) onLine(line);
        newline = buffer.indexOf("\n");
      }
    },
    end() {
      const line = buffer.trim();
      buffer = "";
      if (line) onLine(line);
    },
  };
}

/** Reads a newline-delimited JSON response body, calling `onEvent` for each object. */
export async function readNdjson(body: ReadableStream<Uint8Array>, onEvent: (event: unknown) => void) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  const parser = createLineParser((line) => onEvent(JSON.parse(line)));
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    parser.push(decoder.decode(value, { stream: true }));
  }
  parser.push(decoder.decode());
  parser.end();
}
