"use client"

import { useEffect, useRef } from "react"
import type { SSEEvent } from "@/lib/types"

interface Props {
  events: SSEEvent[]
}

const MAX_DISPLAY = 100

export default function ActivityFeed({ events }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const visible = events.slice(-MAX_DISPLAY)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [events.length])

  return (
    <div className="h-64 overflow-y-auto rounded-lg border border-zinc-200 bg-zinc-950 p-3 font-mono text-xs">
      {visible.length === 0 ? (
        <p className="pt-8 text-center text-zinc-600">Waiting for events…</p>
      ) : (
        <ul className="space-y-1">
          {visible.map((ev, i) => (
            <li key={i} className="flex flex-wrap gap-x-2 text-zinc-300">
              <EventLine event={ev} />
            </li>
          ))}
        </ul>
      )}
      <div ref={bottomRef} />
    </div>
  )
}

function hhmmss(): string {
  return new Date().toLocaleTimeString("en-US", { hour12: false })
}

function toSeconds(ms: number): string {
  return `${(ms / 1000).toFixed(2)}s`
}

function EventLine({ event }: { event: SSEEvent }) {
  if (event.event === "task_update") {
    const icon =
      event.status === "SUCCESS"    ? "✅"
      : event.status === "FAILED"  ? "❌"
      : "🔄"
    return (
      <>
        <span className="text-zinc-500">[{hhmmss()}]</span>
        <span className="text-zinc-400">[{event.worker_id || "—"}]</span>
        <span>{icon}</span>
        <span className="text-white">{event.filename}</span>
        {event.duration_ms > 0 && (
          <span className="text-zinc-500">— {toSeconds(event.duration_ms)}</span>
        )}
      </>
    )
  }

  if (event.event === "worker_status") {
    return (
      <>
        <span className="text-zinc-500">[{hhmmss()}]</span>
        <span className="text-yellow-400">[{event.worker_id}]</span>
        <span>⚙️</span>
        <span className="text-yellow-300">{event.status}</span>
        {event.current_filename && (
          <span className="text-zinc-500">{event.current_filename}</span>
        )}
      </>
    )
  }

  // batch_complete
  return (
    <>
      <span className="text-zinc-500">[{hhmmss()}]</span>
      <span className="text-emerald-400">
        🏁 Batch complete — {event.completed}/{event.total} — {event.speedup_factor}× speedup
      </span>
    </>
  )
}
