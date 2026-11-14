"use client";

import { useEffect, useState } from "react";
import { Download, ExternalLink } from "lucide-react";
import { adminFetch, CoverageReport } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function AdminCoveragePage() {
  const [report, setReport] = useState<CoverageReport | null>(null);
  const [cat, setCat] = useState("ALL");
  const [st, setSt] = useState("ALL");
  const [search, setSearch] = useState("");

  useEffect(() => {
    adminFetch<CoverageReport>("/api/v1/admin/coverage")
      .then(setReport)
      .catch(console.error);
  }, []);

  const rows = (report?.platforms || []).filter((p) => {
    if (cat !== "ALL" && p.category !== cat) return false;
    if (st !== "ALL" && p.implementation_status !== st) return false;
    if (
      search.trim() &&
      !p.name.toLowerCase().includes(search.toLowerCase()) &&
      !p.connector_key.toLowerCase().includes(search.toLowerCase())
    ) {
      return false;
    }
    return true;
  });

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl border border-slate-200 p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            78-Platform Coverage Matrix
          </h1>
          <p className="text-sm text-slate-600">
            58 ATS + 20 Job-Board platforms with live cryptographic verification
            evidence.
          </p>
        </div>
        <div className="flex gap-2">
          <a
            href="/api/v1/platforms/coverage/export?format=csv"
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-slate-900 text-white text-xs font-semibold"
          >
            <Download className="w-3.5 h-3.5" />
            CSV
          </a>
          <a
            href="/api/v1/platforms/coverage/export?format=json"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-slate-200 text-slate-700 text-xs font-semibold"
          >
            <Download className="w-3.5 h-3.5" />
            JSON
          </a>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
        <div className="flex flex-wrap gap-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by platform name or key..."
            className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs flex-1 min-w-[200px]"
          />
          <select
            value={cat}
            onChange={(e) => setCat(e.target.value)}
            className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs"
          >
            <option value="ALL">All Categories (78)</option>
            <option value="ATS">ATS (58)</option>
            <option value="JOB_BOARD">Job Boards (20)</option>
          </select>
          <select
            value={st}
            onChange={(e) => setSt(e.target.value)}
            className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs"
          >
            <option value="ALL">All States</option>
            <option value="VERIFIED">VERIFIED</option>
            <option value="NOT_IMPLEMENTED">NOT_IMPLEMENTED</option>
          </select>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 uppercase text-slate-500">
                <th className="py-2.5 pr-3">Platform</th>
                <th className="py-2.5 pr-3">Cat</th>
                <th className="py-2.5 pr-3">Status</th>
                <th className="py-2.5 pr-3">Health</th>
                <th className="py-2.5 pr-3">Sources</th>
                <th className="py-2.5 pr-3">Jobs</th>
                <th className="py-2.5 pr-3">Avg ms</th>
                <th className="py-2.5">Evidence / Sample</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((p) => (
                <tr key={p.connector_key} className="hover:bg-slate-50">
                  <td className="py-2.5 pr-3 font-semibold text-slate-900">
                    {p.name}
                    <div className="font-mono text-[10px] text-slate-400">
                      {p.connector_key}
                    </div>
                  </td>
                  <td className="py-2.5 pr-3">{p.category}</td>
                  <td className="py-2.5 pr-3">
                    <StatusBadge status={p.implementation_status} />
                  </td>
                  <td className="py-2.5 pr-3">
                    <StatusBadge status={p.health_status} />
                  </td>
                  <td className="py-2.5 pr-3 font-mono">
                    {p.sources_discovered}
                  </td>
                  <td className="py-2.5 pr-3 font-mono font-semibold">
                    {p.active_jobs}
                  </td>
                  <td className="py-2.5 pr-3 font-mono text-slate-500">
                    {p.average_response_time_ms
                      ? `${Math.round(p.average_response_time_ms)}ms`
                      : "—"}
                  </td>
                  <td className="py-2.5">
                    {p.verification_evidence ? (
                      <div>
                        <a
                          href={p.verification_evidence.example_source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-blue-600 hover:underline font-medium"
                        >
                          {p.verification_evidence.sample_job_title?.slice(0, 38) ||
                            "Verified Source"}{" "}
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                    ) : (
                      <span className="text-slate-400">
                        {p.known_limitations || "—"}
                      </span>
                    )}
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
