"use client";
import type { ReactNode } from "react";

interface CallToAction { text: string; onClick?: () => void; icon?: ReactNode; variant: "primary" | "secondary" }
interface HeroLandingProps {
  title: string;
  titleClassName?: string;
  description: string;
  callToActions?: CallToAction[];
  gradientColors?: { from: string; to: string };
  className?: string;
}

export function HeroLanding({ title, titleClassName, description, callToActions = [], gradientColors = { from: "oklch(0.45 0.2 280)", to: "oklch(0.4 0.15 230)" }, className }: HeroLandingProps) {
  return (
    <div className={`relative min-h-[100dvh] w-full overflow-hidden bg-zinc-950 ${className || ""}`}>
      {/* ambient gradient blobs */}
      <div aria-hidden className="absolute inset-x-0 -top-40 -z-10 transform-gpu overflow-hidden blur-3xl sm:-top-80">
        <div style={{ clipPath: "polygon(74.1% 44.1%,100% 61.6%,97.5% 26.9%,85.5% 0.1%,80.7% 2%,72.5% 32.5%,60.2% 62.4%,52.4% 68.1%,47.5% 58.3%,45.2% 34.5%,27.5% 76.7%,0.1% 64.9%,17.9% 100%,27.6% 76.8%,76.1% 97.7%,74.1% 44.1%)", background: `linear-gradient(to top right, ${gradientColors.from}, ${gradientColors.to})` }} className="relative left-[calc(50%-11rem)] aspect-[1155/678] w-[36rem] -translate-x-1/2 rotate-[30deg] opacity-25 sm:left-[calc(50%-30rem)] sm:w-[72rem]" />
      </div>
      <div aria-hidden className="absolute inset-x-0 top-[calc(100%-13rem)] -z-10 transform-gpu overflow-hidden blur-3xl sm:top-[calc(100%-30rem)]">
        <div style={{ clipPath: "polygon(74.1% 44.1%,100% 61.6%,97.5% 26.9%,85.5% 0.1%,80.7% 2%,72.5% 32.5%,60.2% 62.4%,52.4% 68.1%,47.5% 58.3%,45.2% 34.5%,27.5% 76.7%,0.1% 64.9%,17.9% 100%,27.6% 76.8%,76.1% 97.7%,74.1% 44.1%)", background: `linear-gradient(to top right, ${gradientColors.from}, ${gradientColors.to})` }} className="relative left-[calc(50%+3rem)] aspect-[1155/678] w-[36rem] -translate-x-1/2 opacity-25 sm:left-[calc(50%+36rem)] sm:w-[72rem]" />
      </div>

      <div className="relative isolate flex min-h-[100dvh] flex-col items-center justify-center px-6 text-center">
        <div className="mx-auto max-w-4xl">
          <h1 className={titleClassName || "text-5xl font-bold tracking-tight text-foreground sm:text-7xl"}>{title}</h1>
          <p className="mx-auto mt-6 max-w-2xl text-pretty text-base font-medium text-muted-foreground sm:mt-8 sm:text-xl/8">{description}</p>
          {callToActions.length > 0 && (
            <div className="mt-8 flex items-center justify-center gap-x-4 sm:mt-10">
              {callToActions.map((cta, i) => (
                <button key={i} onClick={cta.onClick}
                  className={cta.variant === "primary"
                    ? "glass inline-flex items-center gap-2 rounded-full px-6 py-3 text-sm font-semibold text-white"
                    : "inline-flex items-center gap-1.5 text-sm font-semibold text-foreground transition-colors hover:text-muted-foreground"}>
                  {cta.text}{cta.icon}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
