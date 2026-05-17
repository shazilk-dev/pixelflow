interface Props {
  completed: number
  total: number
}

export default function ProgressBar({ completed, total }: Props) {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0

  return (
    <div className="space-y-1.5">
      <div className="h-3 w-full overflow-hidden rounded-full bg-zinc-200">
        <div
          className="h-full rounded-full bg-blue-500 transition-all duration-300 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-right text-xs text-zinc-500">
        {completed} / {total} images processed ({pct}%)
      </p>
    </div>
  )
}
