import { getBatchResults } from "@/lib/api"
import SpeedupChart from "@/components/SpeedupChart"
import ImageCompare from "@/components/ImageCompare"
import { Clock, Images, Zap, Timer } from "lucide-react"
import type { ReactNode } from "react"
import type { ImageResult } from "@/lib/types"

// ─── Types ────────────────────────────────────────────────────────────────────

interface Props {
  params: Promise<{ batchId: string }>
}

// ─── Page (server component) ──────────────────────────────────────────────────

export default async function ResultsPage({ params }: Props) {
  const { batchId } = await params
  const results = await getBatchResults(batchId)
  const { benchmark, images, status } = results

  const successImages = images.filter((img) => img.status === "SUCCESS")
  const failedImages  = images.filter((img) => img.status === "FAILED")

  const avgDurationMs =
    successImages.length > 0
      ? Math.round(
          successImages.reduce((sum, img) => sum + img.duration_ms, 0) /
          successImages.length
        )
      : 0

  return (
    <main className="min-h-screen bg-[#0f0f0f] px-4 py-12">
      <div className="mx-auto max-w-6xl space-y-10">

        {/* ── Header ───────────────────────────────────────────────────────── */}
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Results</h1>
          <p className="mt-1 font-mono text-xs text-zinc-500 truncate">{batchId}</p>
        </div>

        {/* ── Partial failure banner ───────────────────────────────────────── */}
        {status === "PARTIAL_FAILURE" && failedImages.length > 0 && (
          <div className="rounded-xl border border-red-900 bg-red-950/50 px-4 py-3 text-sm text-red-400">
            {failedImages.length} image{failedImages.length !== 1 ? "s" : ""} failed
            to process after all retries.
          </div>
        )}

        {/* ── Summary stats bar ────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard
            icon={<Clock className="h-4 w-4" />}
            label="Total Time"
            value={`${(benchmark.actual_ms / 1000).toFixed(2)}s`}
          />
          <StatCard
            icon={<Images className="h-4 w-4" />}
            label="Images Processed"
            value={`${successImages.length} / ${images.length}`}
          />
          <StatCard
            icon={<Timer className="h-4 w-4" />}
            label="Avg per Image"
            value={`${avgDurationMs}ms`}
          />
          <StatCard
            icon={<Zap className="h-4 w-4" />}
            label="Speedup"
            value={`${benchmark.speedup_factor}×`}
            highlight
          />
        </div>

        {/* ── Speedup chart ────────────────────────────────────────────────── */}
        <SpeedupChart benchmark={benchmark} />

        {/* ── Image grid (3 columns) ───────────────────────────────────────── */}
        <section>
          <h2 className="mb-4 text-sm font-semibold text-zinc-300">
            Before / After Gallery
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {images.map((img) => (
              <ImageCard key={img.task_id} img={img} />
            ))}
          </div>
        </section>

        {/* ── Download note ────────────────────────────────────────────────── */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 px-4 py-3">
          <p className="text-xs text-zinc-500">
            Processed images saved to{" "}
            <code className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-300">
              /app/data/outputs/{batchId}/
            </code>
          </p>
        </div>

      </div>
    </main>
  )
}

// ─── Image card with FAILED overlay ──────────────────────────────────────────

function ImageCard({ img }: { img: ImageResult }) {
  if (img.status === "FAILED") {
    return (
      <div className="relative overflow-hidden rounded-xl">
        <ImageCompare result={img} />
        {/* Red FAILED overlay */}
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-xl bg-red-950/85 backdrop-blur-[1px]">
          <span className="rounded-full bg-red-500/20 px-3 py-1 text-sm font-bold text-red-400">
            FAILED
          </span>
          <p className="text-xs text-red-400/70">
            Processing error — check worker logs
          </p>
        </div>
      </div>
    )
  }

  return <ImageCompare result={img} />
}

// ─── Stat card ────────────────────────────────────────────────────────────────

function StatCard({
  icon,
  label,
  value,
  highlight = false,
}: {
  icon: ReactNode
  label: string
  value: string
  highlight?: boolean
}) {
  return (
    <div
      className={`rounded-xl border p-4 ${
        highlight
          ? "border-green-800 bg-green-950/50"
          : "border-zinc-800 bg-zinc-900"
      }`}
    >
      <div
        className={`flex items-center gap-2 ${
          highlight ? "text-green-500" : "text-zinc-500"
        }`}
      >
        {icon}
        <span className="text-xs">{label}</span>
      </div>
      <p
        className={`mt-2 text-2xl font-bold tabular-nums ${
          highlight ? "text-green-400" : "text-white"
        }`}
      >
        {value}
      </p>
    </div>
  )
}
