import type { Metadata } from "next";
import { ExportHistoryView } from "@/components/companies/ExportHistoryView";

export const metadata: Metadata = { title: "Export History" };

export default function ExportsPage() {
  return <ExportHistoryView />;
}
