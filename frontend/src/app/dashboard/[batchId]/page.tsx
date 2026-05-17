"use client"

import { useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { useSSE } from "@/hooks/useSSE"
import WorkerCard from "@/components/WorkerCard"
import ActivityFeed from "@/components/ActivityFeed"
import ProgressBar from "@/components/ProgressBar"
import { getBatchStatus, killWorker } from "@/lib/api"
import { logger } from "@/lib/logger"
import type { BatchStatus } from "@/lib/types"

// ─── Constants ────────────────────────────────────────────────────────────────

const MAX_VISIBLE_WORKERS = 3

// ─── Status badge ─────────────────────────────────────────────────────────────

const STATUS_STYLE: Record<BatchStatus, string> = {
  QUEUED:          "bg-zinc-800 text-zinc-400",
  PROCESSING:      "bg-amber-900/60 text-amber-400 animate-pulse",
  COMPLETE:        "bg-green-900/60 text-green-400",
  PARTIAL_FAILURE: "bg-red-900/60 text-red-400",
}

function StatusBadge({ status }: { status: BatchStatus }) {
  return (
    <span className={`rounded-full px-3 py-1 text-xs font-semibold tracking-wide ${STATUS_STYLE[status]}`}>
      {status.replace("_", " ")}
    </span>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { batchId } = useParams<{ batchId: string }>()
  const router = useRouter()

  const { workers, tasks, events, progress, isComplete, error } = useSSE(batchId)

  const [total,    setTotal]    = useState(0)
  const [elapsed,  setElapsed]  = useState(0)
  const [killing,  setKilling]  = useState(false)

  // ── Initial fetch for total count ─────────────────────────────────────────
  useEffect(() => {
    getBatchStatus(batchId)
      .then((s) => setTotal(s.total))
      .catch(() => {})
  }, [batchId])

  // ── Elapsed timer (seconds since mount) ───────────────────────────────────
  useEffect(() => {
    const id = setInterval(() => setElapsed((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [])

  // ── Auto-redirect on completion ───────────────────────────────────────────
  useEffect(() => {
    if (isComplete) {
      router.push(`/results/${batchId}`)
    }
  }, [isComplete, batchId, router])

  // ── Derived state ─────────────────────────────────────────────────────────

  const displayTotal = progress.total > 0 ? progress.total : total

  const completed = progress.total > 0
    ? progress.completed
    : tasks.filter((t) => t.status === "SUCCESS" || t.status === "FAILED").length

  const batchStatus: BatchStatus = isComplete
    ? tasks.some((t) => t.status === "FAILED") ? "PARTIAL_FAILURE" : "COMPLETE"
    : workers.some((w) => w.status === "PROCESSING") ? "PROCESSING"
    : "QUEUED"

  const throughput = elapsed > 0 ? (completed / elapsed).toFixed(1) : "0.0"

  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0")
  const ss = String(elapsed % 60).padStart(2, "0")

  // ── Kill worker_2 handler ─────────────────────────────────────────────────

  const handleKillWorker2 = async () => {
    const confirmed = window.confirm(
      "Kill worker_2? This simulates a node failure.\n\n" +
      "The task it was processing will be reassigned to a live worker."
    )
    if (!confirmed) return

    setKilling(true)
    try {
      await killWorker("worker_2")
      logger.info("Kill signal sent", { worker_id: "worker_2" })
    } catch (err) {
      logger.error("Kill failed", { error: String(err) })
    } finally {
      setKilling(false)
    }
  }

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <main className="min-h-screen bg-[#0f0f0f] px-4 py-8">
      <div className="mx-auto max-w-4xl space-y-8">

        {/* ── Top bar ──────────────────────────────────────────────────────── */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div>
              <h1 className="text-lg font-bold text-white">
                Batch{" "}
                <span className="font-mono text-zinc-400">
                  {batchId.slice(0, 8)}…
                </span>
              </h1>
            </div>
            <StatusBadge status={batchStatus} />
          </div>

          {/* Elapsed timer */}
          <div className="flex items-center gap-3">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2 font-mono text-sm tabular-nums text-zinc-300">
              {mm}:{ss}
            </div>
          </div>
        </div>

        {/* ── Error banner ─────────────────────────────────────────────────── */}
        {error && (
          <div className="rounded-xl border border-red-900 bg-red-950/50 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        {/* ── Worker cards (max 3) ─────────────────────────────────────────── */}
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
              Worker Nodes
            </h2>
            {workers.length > 0 && (
              <span className="text-xs text-zinc-600">
                {workers.length} online
              </span>
            )}
          </div>

          {workers.length === 0 ? (
            <p className="animate-pulse text-sm text-zinc-600">
              Waiting for workers to connect…
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {workers.slice(0, MAX_VISIBLE_WORKERS).map((w) => (
                <WorkerCard key={w.worker_id} worker={w} />
              ))}
            </div>
          )}
        </section>

        {/* ── Progress + throughput ────────────────────────────────────────── */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
              Progress
            </h2>
            <span className="font-mono text-xs text-zinc-500">
              {throughput} images/sec
            </span>
          </div>
          <ProgressBar completed={completed} total={displayTotal} />
        </section>

        {/* ── Activity feed ────────────────────────────────────────────────── */}
        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            Activity Feed
          </h2>
          <ActivityFeed events={events} />
        </section>

        {/* ── Kill Worker 2 (demo only, PROCESSING only) ───────────────────── */}
        {batchStatus === "PROCESSING" && (
          <section className="border-t border-zinc-800 pt-6">
            <div className="flex items-center justify-between gap-4 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
              <div>
                <p className="text-sm font-semibold text-zinc-300">
                  Fault Tolerance Demo
                </p>
                <p className="mt-0.5 text-xs text-zinc-500">
                  Crash worker_2 mid-batch — Celery reassigns the task via{" "}
                  <code className="text-zinc-400">task_acks_late</code>.
                </p>
              </div>
              <button
                onClick={handleKillWorker2}
                disabled={killing}
                className="shrink-0 rounded-xl border border-red-800 bg-red-950/60 px-4 py-2 text-sm font-semibold text-red-400 transition hover:bg-red-900/60 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {killing ? "Sending…" : "⚠️ Kill worker_2"}
              </button>
            </div>
          </section>
        )}

      </div>
    </main>
  )
}
