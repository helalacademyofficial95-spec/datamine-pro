import type { ProjectStatus } from "@/lib/types";
import { Badge, BadgeTone } from "./Badge";

const TONE: Record<ProjectStatus, BadgeTone> = {
  Completed: "ok",
  Running: "brand",
  Queued: "neutral",
  Failed: "bad",
};

export function ProjectStatusBadge({ status }: { status: ProjectStatus }) {
  return (
    <Badge tone={TONE[status]} dot>
      {status}
    </Badge>
  );
}
