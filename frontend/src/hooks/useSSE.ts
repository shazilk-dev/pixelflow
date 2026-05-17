"use client"

import { useEffect, useReducer, useRef } from "react"
import type {
  WorkerSummary,
  TaskSummary,
  SSEEvent,
  SSETaskUpdate,
  SSEWorkerStatus,
  SSEBatchComplete,
} from "@/lib/types"
import { getSSEUrl } from "@/lib/api"
import { logger } from "@/lib/logger"

interface SSEState {
  workers: WorkerSummary[]
  tasks: TaskSummary[]
  events: SSEEvent[]
  progress: { completed: number; total: number }
  isComplete: boolean
  error: string | null
}

type SSEAction =
  | { type: "TASK_UPDATE"; payload: SSETaskUpdate }
  | { type: "WORKER_STATUS"; payload: SSEWorkerStatus }
  | { type: "BATCH_COMPLETE"; payload: SSEBatchComplete }
  | { type: "ERROR"; payload: string }

const INITIAL_STATE: SSEState = {
  workers: [],
  tasks: [],
  events: [],
  progress: { completed: 0, total: 0 },
  isComplete: false,
  error: null,
}

function reducer(state: SSEState, action: SSEAction): SSEState {
  switch (action.type) {
    case "TASK_UPDATE": {
      const updated: TaskSummary = {
        task_id: action.payload.task_id,
        filename: action.payload.filename,
        status: action.payload.status,
        worker_id: action.payload.worker_id,
        duration_ms: action.payload.duration_ms,
        error: action.payload.error,
      }
      const existing = state.tasks.find((t) => t.task_id === updated.task_id)
      const tasks = existing
        ? state.tasks.map((t) => (t.task_id === updated.task_id ? updated : t))
        : [...state.tasks, updated]
      const completed = tasks.filter(
        (t) => t.status === "SUCCESS" || t.status === "FAILED"
      ).length
      return {
        ...state,
        tasks,
        events: [...state.events, action.payload],
        progress: { ...state.progress, completed },
      }
    }
    case "WORKER_STATUS": {
      const { worker_id, status, current_filename, tasks_completed, tasks_failed } =
        action.payload
      const updated: WorkerSummary = {
        worker_id,
        status,
        current_filename,
        tasks_completed,
        tasks_failed,
        last_heartbeat: new Date().toISOString(),
      }
      const existing = state.workers.find((w) => w.worker_id === worker_id)
      const workers = existing
        ? state.workers.map((w) => (w.worker_id === worker_id ? updated : w))
        : [...state.workers, updated]
      return {
        ...state,
        workers,
        events: [...state.events, action.payload],
      }
    }
    case "BATCH_COMPLETE":
      return {
        ...state,
        isComplete: true,
        events: [...state.events, action.payload],
        progress: {
          completed: action.payload.completed,
          total: action.payload.total,
        },
      }
    case "ERROR":
      return { ...state, error: action.payload }
    default:
      return state
  }
}

const MAX_RETRIES = 3
const RETRY_DELAY_MS = 2000

export function useSSE(batchId: string) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE)
  const esRef = useRef<EventSource | null>(null)
  const retriesRef = useRef(0)
  const completeRef = useRef(false)

  useEffect(() => {
    if (!batchId || completeRef.current) return

    function connect() {
      const url = getSSEUrl(batchId)
      const es = new EventSource(url)
      esRef.current = es

      es.addEventListener("task_update", (e: MessageEvent<string>) => {
        retriesRef.current = 0
        dispatch({
          type: "TASK_UPDATE",
          payload: JSON.parse(e.data) as SSETaskUpdate,
        })
      })

      es.addEventListener("worker_status", (e: MessageEvent<string>) => {
        retriesRef.current = 0
        dispatch({
          type: "WORKER_STATUS",
          payload: JSON.parse(e.data) as SSEWorkerStatus,
        })
      })

      es.addEventListener("batch_complete", (e: MessageEvent<string>) => {
        completeRef.current = true
        dispatch({
          type: "BATCH_COMPLETE",
          payload: JSON.parse(e.data) as SSEBatchComplete,
        })
        es.close()
      })

      es.onerror = () => {
        es.close()
        if (completeRef.current) return
        if (retriesRef.current < MAX_RETRIES) {
          retriesRef.current += 1
          logger.warn("SSE connection lost, retrying", { attempt: retriesRef.current })
          setTimeout(connect, RETRY_DELAY_MS)
        } else {
          logger.error("SSE max retries reached")
          dispatch({ type: "ERROR", payload: "Connection lost. Refresh to retry." })
        }
      }
    }

    connect()

    return () => {
      esRef.current?.close()
    }
  }, [batchId])

  return state
}
