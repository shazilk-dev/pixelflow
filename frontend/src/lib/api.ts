import type {
  BatchCreatedResponse,
  BatchStatusResponse,
  BatchResultsResponse,
  WorkersStatusResponse,
} from "@/lib/types"

// Server components run inside Docker — use the internal service hostname.
// Browser (client components) use NEXT_PUBLIC_API_URL which resolves on the host.
function getBaseUrl(): string {
  if (typeof window === "undefined") {
    return process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
  }
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
}

export async function submitBatch(formData: FormData): Promise<BatchCreatedResponse> {
  const res = await fetch(`${getBaseUrl()}/api/process-batch`, {
    method: "POST",
    body: formData,
  })
  if (!res.ok) {
    const text = await res.text()
    let message = `Upload failed (${res.status})`
    try {
      const json: unknown = JSON.parse(text)
      if (json && typeof json === "object" && "detail" in json && typeof (json as Record<string, unknown>).detail === "string") {
        message = (json as Record<string, string>).detail
      }
    } catch { /* use generic message */ }
    throw new Error(message)
  }
  return res.json() as Promise<BatchCreatedResponse>
}

export async function getBatchStatus(batchId: string): Promise<BatchStatusResponse> {
  const res = await fetch(`${getBaseUrl()}/api/batch/${batchId}/status`, {
    cache: "no-store",
  })
  if (!res.ok) throw new Error(`getBatchStatus ${res.status}`)
  return res.json() as Promise<BatchStatusResponse>
}

export async function getBatchResults(batchId: string): Promise<BatchResultsResponse> {
  const res = await fetch(`${getBaseUrl()}/api/batch/${batchId}/results`, {
    cache: "no-store",
  })
  if (!res.ok) throw new Error(`getBatchResults ${res.status}`)
  return res.json() as Promise<BatchResultsResponse>
}

export async function getWorkersStatus(): Promise<WorkersStatusResponse> {
  const res = await fetch(`${getBaseUrl()}/api/workers/status`, {
    cache: "no-store",
  })
  if (!res.ok) throw new Error(`getWorkersStatus ${res.status}`)
  return res.json() as Promise<WorkersStatusResponse>
}

export async function killWorker(workerId: string): Promise<void> {
  const res = await fetch(`${getBaseUrl()}/api/demo/kill-worker/${workerId}`, {
    method: "POST",
  })
  if (!res.ok) throw new Error(`killWorker ${res.status}`)
}

export function getSSEUrl(batchId: string): string {
  return `${getBaseUrl()}/api/stream/${batchId}`
}
