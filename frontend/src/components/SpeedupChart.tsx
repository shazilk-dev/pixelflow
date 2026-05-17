"use client"

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
  LabelList,
} from "recharts"
import type { BenchmarkData } from "@/lib/types"

interface Props {
  benchmark: BenchmarkData
}

const toSeconds = (ms: number) => +(ms / 1000).toFixed(2)


export default function SpeedupChart({ benchmark }: Props) {
  const data = [
    {
      label: "1 Worker (Est.)",
      seconds: toSeconds(benchmark.sequential_estimate_ms),
      estimated: true,
    },
    {
      label: "2 Workers (Est.)",
      seconds: toSeconds(benchmark.two_worker_estimate_ms),
      estimated: true,
    },
    {
      label: "3 Workers (Actual)",
      seconds: toSeconds(benchmark.actual_ms),
      estimated: false,
    },
  ]

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-6">
      <h2 className="mb-4 text-sm font-semibold text-zinc-800">
        Parallel Speedup — {benchmark.speedup_factor}× faster with 3 workers
      </h2>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 16, right: 16, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 11, fill: "#71717a" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tickFormatter={(v: number) => `${v}s`}
            tick={{ fontSize: 11, fill: "#71717a" }}
            axisLine={false}
            tickLine={false}
            label={{
              value: "Time (seconds)",
              angle: -90,
              position: "insideLeft",
              offset: -4,
              style: { fontSize: 10, fill: "#a1a1aa" },
            }}
          />
          <Tooltip
            formatter={(value) => {
              if (value === undefined) return ["", "Time"]
              const num = Array.isArray(value) ? Number(value[0]) : Number(value)
              return [`${num.toFixed(2)}s`, "Time (seconds)"]
            }}
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
          />
          <Legend
            content={
              <div className="flex justify-center gap-5 pt-1 text-xs text-zinc-400">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-2 w-3 rounded" style={{ background: "#a1a1aa" }} />
                  Estimated
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-2 w-3 rounded" style={{ background: "#22c55e" }} />
                  Actual (3 workers)
                </span>
              </div>
            }
          />
          <Bar dataKey="seconds" radius={[6, 6, 0, 0]} maxBarSize={80}>
            {data.map((entry, index) => (
              <Cell key={index} fill={entry.estimated ? "#a1a1aa" : "#22c55e"} />
            ))}
            <LabelList
              dataKey="seconds"
              position="top"
              formatter={(v) =>
                typeof v === "number"
                  ? `${v.toFixed(2)}s`
                  : typeof v === "string"
                    ? `${Number(v).toFixed(2)}s`
                    : ""
              }
              style={{ fontSize: 11, fill: "#52525b" }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
