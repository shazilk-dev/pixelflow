"use client"

import { useState, useRef, useCallback } from "react"
import { useRouter } from "next/navigation"
import { Upload, X, Cpu, Loader2 } from "lucide-react"
import { submitBatch } from "@/lib/api"
import { logger } from "@/lib/logger"
import type { Transformation } from "@/lib/types"

// ─── Constants ────────────────────────────────────────────────────────────────

const TRANSFORMATIONS: { key: Transformation; label: string; desc: string }[] = [
  { key: "resize",    label: "Resize",     desc: "800 × 600 px" },
  { key: "grayscale", label: "Grayscale",  desc: "Remove colour" },
  { key: "blur",      label: "Blur",       desc: "Gaussian r=2" },
  { key: "sharpen",   label: "Sharpen",    desc: "Edge enhance" },
  { key: "watermark", label: "Watermark",  desc: "DPC Pipeline" },
]

const ACCEPTED_TYPES = new Set(["image/jpeg", "image/png", "image/webp"])
const MIN_FILES = 5
const MAX_FILES = 30
const MAX_SIZE_BYTES = 5 * 1024 * 1024

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function UploadPage() {
  const router = useRouter()
  const inputRef = useRef<HTMLInputElement>(null)

  const [files,      setFiles]      = useState<File[]>([])
  const [previews,   setPreviews]   = useState<string[]>([])
  const [transforms, setTransforms] = useState<Set<Transformation>>(
    () => new Set<Transformation>(["resize", "grayscale", "watermark"])
  )
  const [numWorkers, setNumWorkers] = useState<1 | 2 | 3>(3)
  const [error,      setError]      = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [dragActive, setDragActive] = useState(false)

  // ── File helpers ─────────────────────────────────────────────────────────

  const mergeFiles = useCallback((incoming: File[], current: File[]): void => {
    const combined = [...current, ...incoming]

    if (combined.length > MAX_FILES) {
      setError(`Maximum ${MAX_FILES} images allowed (you have ${combined.length}).`)
      return
    }

    setError(null)
    setFiles(combined)
    setPreviews(combined.map((f) => URL.createObjectURL(f)))
  }, [])

  const addFiles = useCallback((list: FileList | null, current: File[]) => {
    if (!list) return
    const errs: string[] = []
    const valid: File[] = []

    Array.from(list).forEach((f) => {
      if (!ACCEPTED_TYPES.has(f.type))       errs.push(`"${f.name}" is not JPG/PNG/WebP`)
      else if (f.size > MAX_SIZE_BYTES)       errs.push(`"${f.name}" exceeds 5 MB`)
      else                                    valid.push(f)
    })

    if (errs.length) {
      setError(errs[0])
      return
    }

    mergeFiles(valid, current)
  }, [mergeFiles])

  const removeFile = (index: number) => {
    const next = files.filter((_, i) => i !== index)
    setFiles(next)
    setPreviews(next.map((f) => URL.createObjectURL(f)))
    setError(null)
  }

  // ── Drag-and-drop ─────────────────────────────────────────────────────────

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragActive(false)
    addFiles(e.dataTransfer.files, files)
  }, [addFiles, files])

  // ── Transform toggle ──────────────────────────────────────────────────────

  const toggleTransform = (key: Transformation) => {
    setTransforms((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  // ── Submit ────────────────────────────────────────────────────────────────

  const canSubmit =
    files.length >= MIN_FILES &&
    files.length <= MAX_FILES &&
    transforms.size > 0 &&
    !submitting

  const handleSubmit = async () => {
    if (files.length < MIN_FILES) {
      setError(`Select at least ${MIN_FILES} images (${files.length} selected).`)
      return
    }
    if (transforms.size === 0) {
      setError("Select at least one transformation.")
      return
    }

    setSubmitting(true)
    setError(null)

    try {
      const formData = new FormData()
      files.forEach((f) => formData.append("images", f))
      formData.append("transformations", JSON.stringify([...transforms]))
      formData.append("num_workers", String(numWorkers))

      const result = await submitBatch(formData)
      logger.info("Batch submitted", { batch_id: result.batch_id })
      router.push(`/dashboard/${result.batch_id}`)
    } catch (err) {
      logger.error("Submit failed", { error: String(err) })
      setError(err instanceof Error ? err.message : "Submission failed. Is the backend running?")
      setSubmitting(false)
    }
  }

  // ── Derived labels ────────────────────────────────────────────────────────

  const submitLabel = () => {
    if (submitting) return null // spinner shown instead
    if (files.length === 0)              return "Select 5–30 images to begin"
    if (files.length < MIN_FILES)       return `Need ${MIN_FILES - files.length} more image${MIN_FILES - files.length !== 1 ? "s" : ""}`
    if (transforms.size === 0)          return "Select at least one transformation"
    return `Process ${files.length} Image${files.length !== 1 ? "s" : ""}`
  }

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <main className="min-h-screen bg-[#0f0f0f] px-4 py-12">
      <div className="mx-auto max-w-3xl space-y-6">

        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">
              Distributed Image Processing
            </h1>
            <p className="mt-1 text-sm text-zinc-500">
              Images processed in parallel across Celery worker nodes via Redis.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5 rounded-full border border-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-400">
            <Cpu className="h-3.5 w-3.5" />
            DPC Pipeline
          </div>
        </div>

        {/* Drop zone */}
        <div
          onDragEnter={() => setDragActive(true)}
          onDragLeave={() => setDragActive(false)}
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed py-14 transition-colors
            ${dragActive
              ? "border-blue-500 bg-blue-950/30"
              : "border-zinc-800 bg-zinc-900/60 hover:border-zinc-600 hover:bg-zinc-900"
            }`}
        >
          <div className="rounded-xl bg-zinc-800 p-3">
            <Upload className="h-6 w-6 text-zinc-400" />
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-zinc-300">
              Drag &amp; drop images, or{" "}
              <span className="text-blue-400 underline underline-offset-2">browse</span>
            </p>
            <p className="mt-1 text-xs text-zinc-600">
              JPG · PNG · WebP · Max 5 MB each · 5–30 files
            </p>
          </div>
          <input
            ref={inputRef}
            type="file"
            accept=".jpg,.jpeg,.png,.webp"
            multiple
            className="hidden"
            onChange={(e) => addFiles(e.target.files, files)}
          />
        </div>

        {/* Thumbnail grid + count badge */}
        {files.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-500">
                {files.length} / {MAX_FILES} selected
                {files.length < MIN_FILES && (
                  <span className="ml-2 text-amber-500">
                    ({MIN_FILES - files.length} more needed)
                  </span>
                )}
              </span>
              <button
                onClick={() => { setFiles([]); setPreviews([]); setError(null) }}
                className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors"
              >
                Clear all
              </button>
            </div>
            <div className="grid grid-cols-5 gap-2 sm:grid-cols-7 md:grid-cols-10">
              {files.map((f, i) => (
                <div
                  key={i}
                  className="group relative aspect-square overflow-hidden rounded-lg bg-zinc-800"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={previews[i] ?? ""}
                    alt={f.name}
                    className="h-full w-full object-cover"
                  />
                  <button
                    onClick={(e) => { e.stopPropagation(); removeFile(i) }}
                    className="absolute right-0.5 top-0.5 hidden rounded-full bg-black/80 p-0.5 text-white group-hover:block"
                  >
                    <X className="h-2.5 w-2.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Transformations */}
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
          <h2 className="mb-3 text-sm font-semibold text-zinc-200">Transformations</h2>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-5">
            {TRANSFORMATIONS.map(({ key, label, desc }) => {
              const checked = transforms.has(key)
              return (
                <label
                  key={key}
                  className={`flex cursor-pointer flex-col gap-0.5 rounded-xl border px-3 py-3 transition
                    ${checked
                      ? "border-blue-500 bg-blue-950/50"
                      : "border-zinc-700 hover:border-zinc-600 hover:bg-zinc-800"
                    }`}
                >
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      className="accent-blue-500"
                      checked={checked}
                      onChange={() => toggleTransform(key)}
                    />
                    <span className={`text-xs font-semibold ${checked ? "text-blue-300" : "text-zinc-300"}`}>
                      {label}
                    </span>
                  </div>
                  <span className="pl-5 text-[10px] text-zinc-600">{desc}</span>
                </label>
              )
            })}
          </div>
        </div>

        {/* Worker count */}
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
          <h2 className="mb-3 text-sm font-semibold text-zinc-200">Worker Nodes</h2>
          <div className="flex gap-3">
            {([1, 2, 3] as const).map((n) => (
              <label
                key={n}
                className={`flex cursor-pointer items-center gap-2 rounded-xl border px-5 py-3 transition
                  ${numWorkers === n
                    ? "border-blue-500 bg-blue-950/50 text-blue-300"
                    : "border-zinc-700 text-zinc-400 hover:border-zinc-600 hover:bg-zinc-800"
                  }`}
              >
                <input
                  type="radio"
                  name="workers"
                  value={n}
                  checked={numWorkers === n}
                  onChange={() => setNumWorkers(n)}
                  className="sr-only"
                />
                <Cpu className="h-4 w-4" />
                <span className="text-sm font-medium">
                  {n} Worker{n !== 1 ? "s" : ""}
                </span>
              </label>
            ))}
          </div>
        </div>

        {/* Validation error */}
        {error && (
          <div className="rounded-xl border border-red-900 bg-red-950/50 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        {/* Submit */}
        <button
          disabled={!canSubmit}
          onClick={handleSubmit}
          className="flex w-full items-center justify-center gap-2 rounded-2xl bg-blue-600 py-4 text-sm font-semibold text-white transition hover:bg-blue-500 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Submitting…
            </>
          ) : (
            submitLabel()
          )}
        </button>

      </div>
    </main>
  )
}
