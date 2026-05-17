import type {
  BatchCreatedResponse,
  BatchStatusResponse,
  BatchResultsResponse,
  WorkersStatusResponse,
} from "@/lib/types"

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export async function submitBatch(formData: FormData): Promise<BatchCreatedResponse> {
  const res = await fetch(`${BASE_URL}/api/process-batch`, {
    method: "POST",
    body: formData,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`submitBatch ${res.status}: ${text}`)
  }
  return res.json() as Promise<BatchCreatedResponse>
}

export async function getBatchStatus(batchId: string): Promise<BatchStatusResponse> {
  const res = await fetch(`${BASE_URL}/api/batch/${batchId}/status`, {
    cache: "no-store",
  })
  if (!res.ok) throw new Error(`getBatchStatus ${res.status}`)
  return res.json() as Promise<BatchStatusResponse>
}

export async function getBatchResults(batchId: string): Promise<BatchResultsResponse> {
  const res = await fetch(`${BASE_URL}/api/batch/${batchId}/results`, {
    cache: "no-store",
  })
  if (!res.ok) throw new Error(`getBatchResults ${res.status}`)
  return res.json() as Promise<BatchResultsResponse>
}

export async function getWorkersStatus(): Promise<WorkersStatusResponse> {
  const res = await fetch(`${BASE_URL}/api/workers/status`, {
    cache: "no-store",
  })
  if (!res.ok) throw new Error(`getWorkersStatus ${res.status}`)
  return res.json() as Promise<WorkersStatusResponse>
}

export async function killWorker(workerId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/demo/kill-worker/${workerId}`, {
    method: "POST",
  })
  if (!res.ok) throw new Error(`killWorker ${res.status}`)
}

export function getSSEUrl(batchId: string): string {
  return `${BASE_URL}/api/stream/${batchId}`
}
