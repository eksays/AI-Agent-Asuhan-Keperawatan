"use client";
import dynamic from "next/dynamic";
import { AppProvider, useApp } from "@/components/app-context";

const Welcome = dynamic(() => import("@/components/welcome").then((m) => m.Welcome), { ssr: false, loading: () => <div className="min-h-[100dvh] bg-zinc-950" /> });
const Dashboard = dynamic(() => import("@/components/dashboard").then((m) => m.Dashboard), { ssr: false, loading: () => <div className="min-h-[100dvh] bg-zinc-950" /> });

function Root() {
  const { phase, capabilities } = useApp();
  // The clinical safety disclaimer is relevant inside the app (where AI gives
  // clinical suggestions), not on the marketing landing page — so hide it there.
  if (phase === "welcome") return <Welcome />;
  return (
    <>
      <div className="fixed inset-x-0 top-0 z-[300] border-b border-amber-500/30 bg-amber-950/95 px-3 py-2 text-center text-xs font-medium text-amber-50 shadow-lg backdrop-blur">
        {capabilities.safety_notice} Unsupported or unverified features are disabled.
        {capabilities.metadata_unavailable ? " Capability metadata unavailable; unsafe features are disabled." : ""}
      </div>
      <div className="pt-9"><Dashboard /></div>
    </>
  );
}

export default function Home() {
  return (<AppProvider><Root /></AppProvider>);
}
