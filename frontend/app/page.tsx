"use client";
import dynamic from "next/dynamic";
import { AppProvider, useApp } from "@/components/app-context";

const Welcome = dynamic(() => import("@/components/welcome").then((m) => m.Welcome), { ssr: false, loading: () => <div className="min-h-[100dvh] bg-zinc-950" /> });
const Dashboard = dynamic(() => import("@/components/dashboard").then((m) => m.Dashboard), { ssr: false, loading: () => <div className="min-h-[100dvh] bg-zinc-950" /> });

function Root() {
  const { phase } = useApp();
  return phase === "welcome" ? <Welcome /> : <Dashboard />;
}

export default function Home() {
  return (<AppProvider><Root /></AppProvider>);
}
