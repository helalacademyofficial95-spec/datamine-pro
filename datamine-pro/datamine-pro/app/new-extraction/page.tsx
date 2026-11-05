import type { Metadata } from "next";
import { NewExtractionView } from "@/components/extraction/NewExtractionView";

export const metadata: Metadata = { title: "New Extraction" };

export default function NewExtractionPage() {
  return <NewExtractionView />;
}
