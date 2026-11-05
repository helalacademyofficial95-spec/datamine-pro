"use client";

import { Menu, Moon, Sun } from "lucide-react";
import { useTheme } from "@/context/ThemeContext";
import { SampleBadge } from "@/components/ui/Badge";
import { isBackendConfigured } from "@/lib/api/client";

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line bg-canvas/80 px-4 backdrop-blur-md sm:px-6 lg:px-8">
      <button className="btn-ghost -ml-2 p-2 lg:hidden" onClick={onMenu} aria-label="Open menu">
        <Menu className="h-5 w-5" />
      </button>
      <div className="flex-1" />
      <SampleBadge label={isBackendConfigured() ? "Live backend" : "Demo · sample data"} />
      <button
        onClick={toggleTheme}
        className="btn-secondary h-10 w-10 !p-0"
        aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
        title={isDark ? "Light mode" : "Dark mode"}
      >
        {isDark ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}
      </button>
      <div
        className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-cyan-400 text-sm font-bold text-white"
        title="Demo user"
        aria-label="Demo user"
      >
        DM
      </div>
    </header>
  );
}
