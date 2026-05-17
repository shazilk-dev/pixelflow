"use client"

import { useState } from "react"
import { killWorker } from "@/lib/api"
import { logger } from "@/lib/logger"

interface Props {
  workerId: string
}

export default function KillWorkerButton({ workerId }: Props) {
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle")

  const handleClick = async () => {
    setState("sending")
    try {
      await killWorker(workerId)
      logger.info("Kill signal sent", { worker_id: workerId })
      setState("sent")
    } catch (err) {
      logger.error("Kill failed", { error: String(err) })
      setState("error")
    }
  }

  return (
    <button
      onClick={handleClick}
      disabled={state === "sending" || state === "sent"}
      className="rounded-xl border border-red-200 bg-red-50 px-5 py-2.5 text-sm font-medium text-red-600 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {state === "idle" && `⚠️ Demo Only — Kill ${workerId}`}
      {state === "sending" && "Sending signal…"}
      {state === "sent" && `✓ Kill signal sent to ${workerId}`}
      {state === "error" && "Failed — is the worker running?"}
    </button>
  )
}
