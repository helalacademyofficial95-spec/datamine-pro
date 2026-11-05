import { FlaskConical } from "lucide-react";

export function DemoNotice({ children }: { children?: React.ReactNode }) {
  return (
    <div className="mb-6 flex items-start gap-3 rounded-xl border border-dashed border-warn/50 bg-warn/10 px-4 py-3 text-sm">
      <FlaskConical className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden />
      <p className="text-ink/90">
        <strong className="text-warn">Demonstration mode.</strong>{" "}
        {children ?? "All companies shown here are invented sample records. No website has been contacted and no real data has been extracted."}
      </p>
    </div>
  );
}
