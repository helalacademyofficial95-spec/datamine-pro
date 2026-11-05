import type { Metadata } from "next";
import { ProjectsView } from "@/components/extraction/ProjectsView";

export const metadata: Metadata = { title: "My Projects" };

export default function ProjectsPage() {
  return <ProjectsView />;
}
