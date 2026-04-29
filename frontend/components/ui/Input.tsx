import { InputHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...props }, ref) {
    return (
      <input
        ref={ref}
        className={cn(
          "w-full bg-bg-elevated border border-line rounded-md px-3 py-2 text-sm text-text-bright",
          "placeholder:text-text-muted focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent",
          "transition-colors disabled:opacity-50",
          className,
        )}
        {...props}
      />
    );
  },
);

export function Label({ children, htmlFor }: { children: React.ReactNode; htmlFor?: string }) {
  return (
    <label htmlFor={htmlFor} className="block text-xs uppercase tracking-wider text-text-muted mb-1.5">
      {children}
    </label>
  );
}
