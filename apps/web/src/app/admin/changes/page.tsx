"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { adminFetch, JobChangeItem, formatDateTime } from "@/lib/api";

export default function AdminChangesPage() {
  const [changes, setChanges] = useState<JobChangeItem[]>([]);

  useEffect(() => {
    adminFetch<{ items: JobChangeItem[] }>(
      "/api/v1/admin/changes?page=1&page_size=50"
    )
      .then((res) => setChanges(res.items))
      .catch(console.error);
  }, []);

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl border border-slate-200 p-6">
        <h1 className="text-2xl font-bold text-slate-900">
          Job Field & Lifecycle Change History ({changes.length})
        </h1>
        <p className="text-sm text-slate-600">
          Every detected title, compensation, location, description, or status
          transition across refresh cycles.
        </p>
      </div>

      {changes.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-10 text-center text-sm text-slate-500">
          No field changes or status transitions recorded yet (initial baseline
          snapshots are active). Trigger a source refresh when a posting updates
          to see field-level diffs here.
        </div>
      ) : (
        <div className="space-y-3">
          {changes.map((ch) => (
            <div
              key={ch.id}
              className="bg-white rounded-xl border border-slate-200 p-4 text-xs space-y-2"
            >
              <div className="flex items-center justify-between">
                <div className="font-semibold text-slate-900">
                  {ch.job_id ? (
                    <Link
                      href={`/jobs/${ch.job_id}`}
                      className="text-blue-600 hover:underline"
                    >
                      {ch.job_title || ch.job_id}
                    </Link>
                  ) : (
                    ch.change_type
                  )}{" "}
                  • <span className="font-mono">{ch.change_type}</span>
                </div>
                <span className="text-slate-500">
                  {formatDateTime(ch.detected_at)}
                </span>
              </div>
              <pre className="p-3 rounded-lg bg-slate-50 text-[11px] overflow-x-auto">
                {JSON.stringify(ch.changed_fields, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
