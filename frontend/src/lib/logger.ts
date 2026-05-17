type Level = "info" | "warn" | "error"

interface LogEntry {
  timestamp: string
  level: Level
  message: string
  extra?: Record<string, unknown>
}

function log(level: Level, message: string, extra?: Record<string, unknown>): void {
  if (process.env.NODE_ENV === "production") return
  const entry: LogEntry = {
    timestamp: new Date().toISOString(),
    level,
    message,
    ...(extra ? { extra } : {}),
  }
  console[level](JSON.stringify(entry)) // structured logger — intentional console use
}

export const logger = {
  info: (message: string, extra?: Record<string, unknown>) => log("info", message, extra),
  warn: (message: string, extra?: Record<string, unknown>) => log("warn", message, extra),
  error: (message: string, extra?: Record<string, unknown>) => log("error", message, extra),
}
