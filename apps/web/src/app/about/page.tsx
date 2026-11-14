"use client";

import { useEffect, useState } from "react";
import { Download, CheckCircle2, ShieldAlert, ExternalLink } from "lucide-react";
import { apiGet, CoverageReport } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function AboutCoveragePage() {
  const [report, setReport] = useState<CoverageReport | null>(null);
  const [categoryFilter, setCategoryFilter] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");

  useEffect(() => {
    apiGet<CoverageReport>("/api/v1/platforms/coverage")
      .then(setReport)
      .catch(console.error);
  }, []);

  const filtered = (report?.platforms || []).filter((p) => {
    if (categoryFilter !== "ALL" && p.category !== categoryFilter) return false;
    if (statusFilter !== "ALL" && p.implementation_status !== statusFilter)
      return false;
    return true;
  });

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">
      <div className="bg-white rounded-2xl border border-slate-200 p-6 sm:p-8">
        <h1 className="text-3xl font-bold text-slate-900">
          Platform Transparency & 78-Platform Coverage Matrix
        </h1>
        <p className="mt-3 text-slate-600 leading-relaxed max-w-4xl">
          Jobre tracks <strong>58 Applicant Tracking Systems (ATS)</strong> and{" "}
          <strong>20 Job-Board Software Platforms</strong> (78 platforms total).
          Under our strict engineering integrity rules, no connector is ever marked{" "}
          <code className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 text-xs font-semibold">
            VERIFIED
          </code>{" "}
          unless it has executed against a real, live public source, saved a
          compressed raw payload snapshot, normalized valid vacancy records into
          PostgreSQL, and recorded cryptographic run evidence.
        </p>

        <div className="mt-6 flex flex-wrap gap-3">
          <a
            href="/api/v1/platforms/coverage/export?format=csv"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-900 text-white text-xs font-semibold hover:bg-blue-600 transition-colors"
          >
            <Download className="w-4 h-4" />
            Export Coverage CSV
          </a>
          <a
            href="/api/v1/platforms/coverage/export?format=json"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 text-slate-700 text-xs font-semibold hover:bg-slate-50"
          >
            <Download className="w-4 h-4" />
            Export Coverage JSON
          </a>
        </div>

        <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <div className="p-4 rounded-xl bg-emerald-50/60 border border-emerald-200">
            <div className="font-semibold text-emerald-900 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              ATS Platforms: {report?.category_breakdown?.ATS?.verified ?? "—"} /{" "}
              {report?.category_breakdown?.ATS?.total ?? 58} Live Verified
            </div>
            <p className="mt-1 text-xs text-emerald-800">
              Includes Greenhouse, Ashby, Lever.co, Workday, SmartRecruiters,
              Workable, Recruitee, Breezy HR, Pinpoint, Personio, Polymer, Gem.com,
              Teamtailor, Manatal, JazzHR, Trakstar, and BambooHR.
            </p>
          </div>
          <div className="p-4 rounded-xl bg-blue-50/60 border border-blue-200">
            <div className="font-semibold text-blue-900 flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-blue-600" />
              Job-Board Engines:{" "}
              {report?.category_breakdown?.JOB_BOARD?.verified ?? "—"} /{" "}
              {report?.category_breakdown?.JOB_BOARD?.total ?? 20} Live Verified
            </div>
            <p className="mt-1 text-xs text-blue-800">
              Includes Niceboard, WP Job Manager, JobBoard.io, SmartJobBoard, and
              Jobboardly. Remaining catalog entries are explicitly tracked as
              NOT_IMPLEMENTED with documented auth/WAF/tenant constraints.
            </p>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
          <h2 className="text-lg font-bold text-slate-900">
            Live Evidence-Backed Catalog ({filtered.length} shown)
          </h2>
          <div className="flex flex-wrap gap-2">
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium"
            >
              <option value="ALL">All Categories (78)</option>
              <option value="ATS">ATS Platforms (58)</option>
              <option value="JOB_BOARD">Job-Board Platforms (20)</option>
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium"
            >
              <option value="ALL">All Statuses</option>
              <option value="VERIFIED">VERIFIED Only</option>
              <option value="NOT_IMPLEMENTED">NOT_IMPLEMENTED Only</option>
            </select>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 uppercase text-slate-500">
                <th className="py-2.5 pr-3">Platform</th>
                <th className="py-2.5 pr-3">Category</th>
                <th className="py-2.5 pr-3">Status</th>
                <th className="py-2.5 pr-3">Sources</th>
                <th className="py-2.5 pr-3">Active Jobs</th>
                <th className="py-2.5 pr-3">Extraction Method</th>
                <th className="py-2.5">Verification Evidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((p) => (
                <tr key={p.connector_key} className="hover:bg-slate-50">
                  <td className="py-3 pr-3 font-semibold text-slate-900">
                    {p.name}
                    <div className="font-mono text-[10px] text-slate-400">
                      {p.connector_key}
                    </div>
                  </td>
                  <td className="py-3 pr-3 text-slate-600">{p.category}</td>
                  <td className="py-3 pr-3">
                    <StatusBadge status={p.implementation_status} />
                  </td>
                  <td className="py-3 pr-3 font-mono">{p.sources_discovered}</td>
                  <td className="py-3 pr-3 font-mono font-semibold">
                    {p.active_jobs}
                  </td>
                  <td className="py-3 pr-3 text-slate-600 max-w-xs">
                    {p.extraction_method}
                  </td>
                  <td className="py-3 text-slate-600">
                    {p.verification_evidence ? (
                      <div>
                        <a
                          href={p.verification_evidence.example_source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-blue-600 hover:underline font-medium"
                        >
                          Live Source <ExternalLink className="w-3 h-3" />
                        </a>
                        <div className="text-[10px] font-mono text-slate-400">
                          Run:{" "}
                          {p.verification_evidence.verification_run_id?.slice(0, 8)}
                        </div>
                      </div>
                    ) : (
                      <span className="text-slate-400">
                        {p.known_limitations || "Pending connector implementation"}
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
