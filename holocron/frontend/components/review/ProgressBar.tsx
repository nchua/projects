interface Props {
  current: number;
  total: number;
}

export default function ProgressBar({ current, total }: Props) {
  const pct = total > 0 ? ((current + 1) / total) * 100 : 0;

  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-1 bg-surface rounded-full overflow-hidden">
        <div
          className="h-full bg-amber rounded-full transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-muted whitespace-nowrap">
        {current + 1} of {total}
      </span>
    </div>
  );
}
