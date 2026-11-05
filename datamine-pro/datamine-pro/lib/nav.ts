import { Download, Filter, FolderKanban, LayoutDashboard, PlusCircle, Settings, Table2, type LucideIcon } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/new-extraction", label: "New Extraction", icon: PlusCircle },
  { href: "/projects", label: "My Projects", icon: FolderKanban },
  { href: "/companies", label: "Extracted Companies", icon: Table2 },
  { href: "/filters", label: "Data Filters", icon: Filter },
  { href: "/exports", label: "Export History", icon: Download },
  { href: "/settings", label: "Settings", icon: Settings },
];
