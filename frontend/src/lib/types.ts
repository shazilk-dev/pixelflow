// Status enums — exact strings used throughout the system
export type TaskStatus = "QUEUED" | "PROCESSING" | "SUCCESS" | "FAILED"
export type BatchStatus = "QUEUED" | "PROCESSING" | "COMPLETE" | "PARTIAL_FAILURE"
export type WorkerStatus = "IDLE" | "PROCESSING" | "OFFLINE"
export type Transformation = "resize" | "grayscale" | "blur" | "sharpen" | "watermark"

export interface TaskSummary {
  task_id: string
  filename: string
  status: TaskStatus
  worker_id: string
  duration_ms: number
  error: string
}

export interface WorkerSummary {
  worker_id: string
  status: WorkerStatus
  current_filename: string
  tasks_completed: number
  tasks_failed: number
  last_heartbeat: string
}

export interface BenchmarkData {
  sequential_estimate_ms: number
  two_worker_estimate_ms: number
  actual_ms: number
  speedup_factor: number
}

export interface ImageResult {
  task_id: string
  filename: string
  status: TaskStatus
  worker_id: string
  duration_ms: number
  original_size_kb: number
  output_size_kb: number
  original_url: string
  processed_url: string
  transformations_applied: Transformation[]
}

export interface BatchCreatedResponse {
  batch_id: string
  total_images: number
  status: string
  created_at: string
}

export interface BatchStatusResponse {
  batch_id: string
  status: BatchStatus
  total: number
  completed: number
  failed: number
  elapsed_ms: number
  throughput: number
  tasks: TaskSummary[]
}

export interface BatchResultsResponse {
  batch_id: string
  status: BatchStatus
  images: ImageResult[]
  benchmark: BenchmarkData
}

export interface WorkersStatusResponse {
  workers: WorkerSummary[]
}

// SSE event payloads — received via useSSE hook
export interface SSETaskUpdate {
  event: "task_update"
  task_id: string
  batch_id: string
  filename: string
  status: TaskStatus
  worker_id: string
  duration_ms: number
  attempt: number
  error: string
}

export interface SSEWorkerStatus {
  event: "worker_status"
  worker_id: string
  status: WorkerStatus
  current_filename: string
  tasks_completed: number
  tasks_failed: number
}

export interface SSEBatchComplete {
  event: "batch_complete"
  batch_id: string
  total: number
  completed: number
  failed: number
  actual_ms: number
  sequential_estimate_ms: number
  speedup_factor: number
}

export type SSEEvent = SSETaskUpdate | SSEWorkerStatus | SSEBatchComplete
