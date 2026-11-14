"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Building2, Search, Globe } from "lucide-react";
import { apiGet, CompanySummary } from "@/lib/api";

interface CompaniesPageRes {
  items: CompanySummary[];
  total: number;
  page: number;
  total_pages: number;
}

export default function CompaniesPage() {
  const [q, setQ] = useState("");
  const [data, setData] = useState<CompaniesPageRes | null>(null);
  const [loading, setLoading] = useState(true);

  const load = (query: string) => {
    setLoading(true);
    const params = new URLSearchParams({ page: "1", page_size: "60" });
    if (query.trim()) params.set("q", query.trim());
    apiGet<CompaniesPageRes>(`/api/v1/companies?${params.toString()}`)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load("");
  }, []);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Indexed Employers ({data?.total ?? "…"})
          </h1>
          <p className="text-sm text-slate-600">
            Companies discovered via direct ATS career portals and verified job boards.
          </p>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            load(q);
          }}
          className="flex gap-2"
        >
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
            <input
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Filter employers..."
              className="pl-9 pr-3 py-2 rounded-xl border border-slate-200 bg-white text-sm"
            />
          </div>
          <button
            type="submit"
            className="px-4 py-2 rounded-xl bg-slate-900 text-white text-sm font-semibold"
          >
            Filter
          </button>
        </form>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((n) => (
            <div
              key={n}
              className="h-28 rounded-xl bg-white border border-slate-200 animate-pulse"
            />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {data?.items.map((c) => (
            <Link
              key={c.id}
              href={`/companies/${c.id}`}
              className="bg-white rounded-xl border border-slate-200 p-5 hover:border-blue-500 transition-colors flex flex-col justify-between"
            >
              <div>
                <div className="flex items-start justify-between gap-2">
                  <h2 className="font-semibold text-slate-900 flex items-center gap-2">
                    <Building2 className="w-4 h-4 text-blue-600 shrink-0" />
                    {c.name}
                  </h2>
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                    {c.active_jobs_count} active
                  </span>
                </div>
                {c.website_url && (
                  <p className="mt-1.5 text-xs text-slate-500 truncate flex items-center gap-1">
                    <Globe className="w-3 h-3" />
                    {c.website_url}
                  </p>
                )}
              </div>
              <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
                <span>{c.sources_count} direct source(s)</span>
                <span className="text-blue-600 font-semibold">View openings →</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
