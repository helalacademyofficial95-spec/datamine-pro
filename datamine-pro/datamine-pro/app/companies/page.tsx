import type { Metadata } from "next";
import { CompaniesView } from "@/components/companies/CompaniesView";

export const metadata: Metadata = { title: "Extracted Companies" };

export default function CompaniesPage() {
  return <CompaniesView />;
}
