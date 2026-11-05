import type { Metadata } from "next";
import { FiltersView } from "@/components/filters/FiltersView";

export const metadata: Metadata = { title: "Data Filters" };

export default function FiltersPage() {
  return <FiltersView />;
}
