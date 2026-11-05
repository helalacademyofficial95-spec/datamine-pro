import type { VerificationStatus } from "@/lib/types";
import { Badge, BadgeTone } from "./Badge";

const TONE: Record<VerificationStatus, BadgeTone> = {
  Verified: "ok",
  "Partially verified": "warn",
  Unverified: "neutral",
};

export function VerificationBadge({ status }: { status: VerificationStatus }) {
  return (
    <Badge tone={TONE[status]} dot>
      {status}
    </Badge>
  );
}
