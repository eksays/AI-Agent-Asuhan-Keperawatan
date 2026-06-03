"use client";
import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

type BannerProps = {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  show?: boolean;
  onHide?: () => void;
  action?: React.ReactNode;
  closable?: boolean;
  className?: string;
};

export function Banner({ title, description, icon, show, onHide, action, closable = true, className }: BannerProps) {
  if (!show) return null;
  return (
    <div role="alert" className={cn("relative overflow-hidden rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200", className)}>
      <div className="flex items-center justify-between gap-4">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          {icon && <div className="flex-shrink-0 text-red-300">{icon}</div>}
          <div className="min-w-0">
            <p className="font-semibold text-red-100">{title}</p>
            {description && <p className="text-xs text-red-200/80">{description}</p>}
          </div>
        </div>
        <div className="flex flex-shrink-0 items-center gap-2">
          {action}
          {closable && <button onClick={onHide} className="rounded-md p-1 text-red-200/70 hover:bg-white/10 hover:text-red-100"><X className="h-4 w-4" /></button>}
        </div>
      </div>
    </div>
  );
}
