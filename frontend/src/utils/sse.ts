export interface RawSseEvent {
  event: string
  data: string
}

export class SseParser {
  private buffer = ''

  push(chunk: string): RawSseEvent[] {
    this.buffer += chunk.replace(/\r\n/g, '\n')
    const events: RawSseEvent[] = []

    while (true) {
      const boundary = this.buffer.indexOf('\n\n')
      if (boundary < 0) {
        break
      }

      const block = this.buffer.slice(0, boundary)
      this.buffer = this.buffer.slice(boundary + 2)

      const parsed = parseEventBlock(block)
      if (parsed) {
        events.push(parsed)
      }
    }

    return events
  }

  finish(): RawSseEvent[] {
    const tail = this.buffer.trim()
    this.buffer = ''

    if (!tail) {
      return []
    }

    const parsed = parseEventBlock(tail)
    return parsed ? [parsed] : []
  }
}

function parseEventBlock(block: string): RawSseEvent | null {
  let event = 'message'
  const dataLines: string[] = []

  for (const line of block.split('\n')) {
    if (!line || line.startsWith(':')) {
      continue
    }

    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
      continue
    }

    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  }

  if (dataLines.length === 0) {
    return null
  }

  return {
    event,
    data: dataLines.join('\n'),
  }
}
