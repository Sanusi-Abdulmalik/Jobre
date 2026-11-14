import React from "react";

export function StatusBadge({ status }: { status: string }) {
  const s = (status || "UNKNOWN").toUpperCase();
  let cls = "bg-slate-100 text-slate-700 border-slate-200";
  if (["VERIFIED", "ACTIVE", "SUCCEEDED", "HEALTHY", "AUTO_MERGED", "APPROVED"].includes(s)) {
    cls = "bg-emerald-50 text-emerald-700 border-emerald-200";
  } else if (["IMPLEMENTED", "TESTED", "RUNNING", "HYBRID", "HIGH"].includes(s)) {
    cls = "bg-blue-50 text-blue-700 border-blue-200";
  } else if (["POSSIBLY_CLOSED", "DEGRADED", "PENDING_REVIEW", "PARTIAL", "REMOTE"].includes(s)) {
    cls = "bg-amber-50 text-amber-800 border-amber-200";
  } else if (["FAILED", "CLOSED", "EXPIRED", "DISABLED", "REJECTED"].includes(s)) {
    cls = "bg-rose-50 text-rose-700 border-rose-200";
  }
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${cls}`}
    >
      {s.replace(/_/g, " ")}
    </span>
  );
}
