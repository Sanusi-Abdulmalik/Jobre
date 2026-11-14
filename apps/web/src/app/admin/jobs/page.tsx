"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, JobSummary, formatSalary, formatDateShort } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function AdminJobsPage() {
  const [status, setStatus] = useState("ACTIVE");
  const [q, setQ] = useState("");
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [total, setTotal] = useState(0);

  const load = (targetStatus: string, query: string) => {
    const params = new URLSearchParams({
      status: targetStatus,
      page: "1",
      page_size: "50",
    });
    if (query.trim()) params.set("q", query.trim());
    apiGet<{ items: JobSummary[]; total: number }>(
      `/api/v1/jobs/search?${params.toString()}`
    )
      .then((res) => {
        setJobs(res.items);
        setTotal(res.total);
      })
      .catch(console.error);
  };

  useEffect(() => {
    load(status, q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl border border-slate-200 p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Normalized Job Records ({total})
          </h1>
          <p className="text-sm text-slate-600">
            Canonical PostgreSQL job entities with lifecycle states and source
            counts.
          </p>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            load(status, q);
          }}
          className="flex gap-2"
        >
          <input
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Keyword filter..."
            className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs"
          />
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs"
          >
            <option value="ACTIVE">ACTIVE</option>
            <option value="POSSIBLY_CLOSED">POSSIBLY_CLOSED</option>
            <option value="CLOSED">CLOSED</option>
          </select>
          <button
            type="submit"
            className="px-3 py-1.5 rounded-lg bg-slate-900 text-white text-xs font-semibold"
          >
            Search
          </button>
        </form>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-5 overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 uppercase text-slate-500">
              <th className="py-2.5 pr-3">Title</th>
              <th className="py-2.5 pr-3">Employer</th>
              <th className="py-2.5 pr-3">Workplace</th>
              <th className="py-2.5 pr-3">Compensation</th>
              <th className="py-2.5 pr-3">Sources</th>
              <th className="py-2.5 pr-3">Status</th>
              <th className="py-2.5">First Seen</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {jobs.map((j) => (
              <tr key={j.id} className="hover:bg-slate-50">
                <td className="py-2.5 pr-3 font-semibold">
                  <Link
                    href={`/jobs/${j.id}`}
                    className="text-blue-600 hover:underline"
                  >
                    {j.title}
                  </Link>
                </td>
                <td className="py-2.5 pr-3 text-slate-700">{j.company_name}</td>
                <td className="py-2.5 pr-3">
                  <StatusBadge status={j.workplace_type} />
                </td>
                <td className="py-2.5 pr-3 text-slate-600">
                  {formatSalary(j) || "null"}
                </td>
                <td className="py-2.5 pr-3 font-mono font-bold">
                  {j.source_count}
                </td>
                <td className="py-2.5 pr-3">
                  <StatusBadge status={j.status} />
                </td>
                <td className="py-2.5 text-slate-500">
                  {formatDateShort(j.first_seen_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
