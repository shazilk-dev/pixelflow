import { Cpu } from "lucide-react"
import type { WorkerSummary } from "@/lib/types"

interface Props {
  worker: WorkerSummary
}

const ringClass: Record<string, string> = {
  PROCESSING: "ring-2 ring-green-400 animate-pulse",
  IDLE:       "ring-2 ring-gray-300",
  OFFLINE:    "ring-2 ring-red-500",
}

export default function WorkerCard({ worker }: Props) {
  const { worker_id, status, current_filename, tasks_completed, tasks_failed } = worker

  return (
    <div
      className={`rounded-xl bg-white p-4 shadow-sm transition-all duration-300 ${ringClass[status] ?? "ring-2 ring-gray-300"}`}
    >
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Cpu className="h-4 w-4 text-zinc-400" />
          <span className="font-mono text-sm font-semibold text-zinc-800">{worker_id}</span>
        </div>
        <StatusBadge status={status} />
      </div>

      <p className="truncate text-xs text-zinc-500">
        {status === "PROCESSING" && current_filename ? current_filename : "Idle"}
      </p>

      <div className="mt-3 flex gap-4 text-xs text-zinc-400">
        <span>{tasks_completed} done</span>
        {tasks_failed > 0 && <span className="text-red-400">{tasks_failed} failed</span>}
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  if (status === "PROCESSING")
    return (
      <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-semibold text-green-700">
        PROCESSING
      </span>
    )
  if (status === "OFFLINE")
    return (
      <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700">
        OFFLINE
      </span>
    )
  return (
    <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-semibold text-zinc-500">
      IDLE
    </span>
  )
}
