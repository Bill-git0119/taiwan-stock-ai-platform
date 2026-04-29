import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/Card";

interface Props {
  label: string;
  value: string;
  delta?: string;
  tone?: "up" | "down" | "neutral";
}

export function StatCard({ label, value, delta, tone = "neutral" }: Props) {
  const toneClass =
    tone === "up"
      ? "text-up"
      : tone === "down"
        ? "text-down"
        : "text-text-muted";
  return (
    <Card hover className="p-4">
      <div className="text-[11px] uppercase tracking-wider text-text-muted">
        {label}
      </div>
      <div className="mt-2 mono text-2xl text-text-bright">{value}</div>
      {delta && (
        <div className={cn("mt-1 mono text-xs", toneClass)}>{delta}</div>
      )}
    </Card>
  );
}
