import Image from "next/image"
import type { ImageResult } from "@/lib/types"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

function toAbsolute(url: string) {
  return url.startsWith("/") ? `${API_URL}${url}` : url
}

interface Props {
  result: ImageResult
}

export default function ImageCompare({ result }: Props) {
  const {
    filename,
    original_url,
    processed_url,
    original_size_kb,
    output_size_kb,
    worker_id,
    duration_ms,
    status,
  } = result

  const fallback = !processed_url || status === "FAILED"

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white">
      {/* Side-by-side panels */}
      <div className="grid grid-cols-2 divide-x divide-zinc-200">
        <Panel url={toAbsolute(original_url)} label="Original" filename={filename} />
        <Panel
          url={toAbsolute(fallback ? original_url : processed_url)}
          label="Processed"
          filename={filename}
          dimmed={fallback}
        />
      </div>

      {/* Footer */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-zinc-100 px-3 py-2">
        <p className="truncate text-xs text-zinc-400 max-w-[50%]">{filename}</p>
        <div className="flex items-center gap-3 text-xs text-zinc-400">
          {original_size_kb > 0 && output_size_kb > 0 && (
            <span>{original_size_kb}KB → {output_size_kb}KB</span>
          )}
          {worker_id && duration_ms > 0 && (
            <span className="rounded-md bg-zinc-100 px-2 py-0.5 text-zinc-500">
              Processed by {worker_id} in {duration_ms}ms
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

function Panel({
  url,
  label,
  filename,
  dimmed = false,
}: {
  url: string
  label: string
  filename: string
  dimmed?: boolean
}) {
  return (
    <div className="flex flex-col">
      <div
        className={`relative aspect-video w-full overflow-hidden bg-zinc-100 ${dimmed ? "opacity-40" : ""}`}
      >
        <Image
          src={url}
          alt={`${label}: ${filename}`}
          fill
          className="object-cover"
          sizes="(max-width: 768px) 50vw, 33vw"
          unoptimized
        />
      </div>
      <p className="px-3 py-1.5 text-xs font-medium text-zinc-600">{label}</p>
    </div>
  )
}
