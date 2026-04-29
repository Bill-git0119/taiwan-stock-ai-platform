import { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Card({
  children,
  className,
  hover = false,
}: {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}) {
  return (
    <div
      className={cn(
        "panel",
        hover &&
          "transition-all duration-200 hover:border-accent/40 hover:shadow-[0_0_0_1px_rgba(41,98,255,0.25)] hover:-translate-y-[1px]",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  right,
  className,
}: {
  title: string;
  subtitle?: string;
  right?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-between px-5 py-3 border-b border-line",
        className,
      )}
    >
      <div>
        <h2 className="text-sm font-semibold text-text-bright tracking-tight">
          {title}
        </h2>
        {subtitle && (
          <p className="text-[11px] text-text-muted mt-0.5">{subtitle}</p>
        )}
      </div>
      {right}
    </div>
  );
}
