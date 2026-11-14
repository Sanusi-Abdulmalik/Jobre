"use client";

import { useEffect, useState } from "react";
import { Eye } from "lucide-react";
import { adminFetch, formatDateTime } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

interface RunItem {
  id: string;
  source_id: string;
  source_name: string;
  platform_name: string | null;
  connector_id: string;
  trigger_type: string;
  status: string;
  is_complete_snapshot: boolean;
  http_status: number | null;
  started_at: string;
  duration_ms: number | null;
  jobs_discovered: number;
  jobs_created: number;
  jobs_updated: number;
  jobs_deduplicated: number;
  jobs_closed: number;
  error_summary: string | null;
}

export default function AdminRunsPage() {
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [selectedDetail, setSelectedDetail] = useState<Record<
    string,
    unknown
  > | null>(null);

  useEffect(() => {
    adminFetch<{ items: RunItem[] }>("/api/v1/admin/runs?page=1&page_size=50")
      .then((res) => setRuns(res.items))
      .catch(console.error);
  }, []);

  const inspectRun = async (id: string) => {
    const res = await adminFetch<Record<string, unknown>>(
      `/api/v1/admin/runs/${id}`
    );
    setSelectedDetail(res);
  };

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl border border-slate-200 p-6">
        <h1 className="text-2xl font-bold text-slate-900">
          Ingestion Runs & Raw Snapshot Ledger
        </h1>
        <p className="text-sm text-slate-600">
          Audit every connector run, HTTP status, discovered/deduplicated job
          counts, and retained compressed raw payload SHA-256 hashes.
        </p>
      </div>

      {selectedDetail && (
        <div className="bg-slate-900 text-slate-100 rounded-2xl p-5 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-emerald-400">
              Raw Run & Snapshot Inspector
            </span>
            <button
              onClick={() => setSelectedDetail(null)}
              className="text-xs text-slate-400 hover:text-white"
            >
              Close
            </button>
          </div>
          <pre className="text-[11px] overflow-x-auto max-h-80">
            {JSON.stringify(selectedDetail, null, 2)}
          </pre>
        </div>
      )}

      <div className="bg-white rounded-2xl border border-slate-200 p-5">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 uppercase text-slate-500">
                <th className="py-2.5 pr-3">Source</th>
                <th className="py-2.5 pr-3">Connector</th>
                <th className="py-2.5 pr-3">Status</th>
                <th className="py-2.5 pr-3">Found / New / Dedup</th>
                <th className="py-2.5 pr-3">Duration</th>
                <th className="py-2.5 pr-3">Started</th>
                <th className="py-2.5">Inspect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {runs.map((r) => (
                <tr key={r.id} className="hover:bg-slate-50">
                  <td className="py-2.5 pr-3 font-medium text-slate-900">
                    {r.source_name}
                  </td>
                  <td className="py-2.5 pr-3 font-mono">{r.connector_id}</td>
                  <td className="py-2.5 pr-3">
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="py-2.5 pr-3 font-mono">
                    {r.jobs_discovered} / {r.jobs_created} /{" "}
                    <span className="text-indigo-600 font-bold">
                      {r.jobs_deduplicated}
                    </span>
                  </td>
                  <td className="py-2.5 pr-3 font-mono text-slate-600">
                    {r.duration_ms ? `${r.duration_ms}ms` : "—"}
                  </td>
                  <td className="py-2.5 pr-3 text-slate-500">
                    {formatDateTime(r.started_at)}
                  </td>
                  <td className="py-2.5">
                    <button
                      onClick={() => inspectRun(r.id)}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 font-semibold"
                    >
                      <Eye className="w-3 h-3" />
                      Snapshots
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
