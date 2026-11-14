"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Building2, ExternalLink, Globe } from "lucide-react";
import { apiGet, JobSummary, formatDateTime } from "@/lib/api";
import { JobCard } from "@/components/JobCard";
import { StatusBadge } from "@/components/StatusBadge";

interface CompanyDetailRes {
  id: string;
  name: string;
  normalized_name: string;
  website_url: string | null;
  description: string | null;
  sources: {
    id: string;
    source_name: string;
    source_url: string;
    platform_name: string | null;
    platform_key: string | null;
    status: string;
    last_successful_sync_at: string | null;
  }[];
  jobs: JobSummary[];
}

export default function CompanyDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const [company, setCompany] = useState<CompanyDetailRes | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiGet<CompanyDetailRes>(`/api/v1/companies/${params.id}`)
      .then(setCompany)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [params.id]);

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-12">
        <div className="h-48 rounded-2xl bg-white border border-slate-200 animate-pulse" />
      </div>
    );
  }

  if (!company) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-12 text-center">
        <p className="text-slate-700 font-medium">Company record not found.</p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <Link
        href="/companies"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900"
      >
        <ArrowLeft className="w-4 h-4" />
        All Employers
      </Link>

      <div className="bg-white rounded-2xl border border-slate-200 p-6 sm:p-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 flex items-center gap-2.5">
              <Building2 className="w-7 h-7 text-blue-600" />
              {company.name}
            </h1>
            {company.website_url && (
              <a
                href={company.website_url}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-flex items-center gap-1.5 text-sm text-blue-600 hover:underline"
              >
                <Globe className="w-4 h-4" />
                {company.website_url}
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
          </div>
          <div className="text-sm font-semibold text-slate-700 bg-slate-100 px-4 py-2 rounded-xl">
            {company.jobs.length} Indexed Openings
          </div>
        </div>

        {company.sources.length > 0 && (
          <div className="mt-6 pt-5 border-t border-slate-100">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
              Registered Direct ATS / Career Sources
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {company.sources.map((s) => (
                <div
                  key={s.id}
                  className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between gap-3 text-xs"
                >
                  <div className="min-w-0">
                    <div className="font-semibold text-slate-900 truncate">
                      {s.source_name}
                    </div>
                    <a
                      href={s.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-600 hover:underline truncate block"
                    >
                      {s.source_url}
                    </a>
                    <div className="text-slate-500 mt-0.5">
                      Last synced: {formatDateTime(s.last_successful_sync_at)}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <StatusBadge status={s.status} />
                    {s.platform_name && (
                      <span className="font-mono text-[11px] text-slate-600">
                        {s.platform_name}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="space-y-3">
        <h2 className="text-lg font-bold text-slate-900">
          Open Positions ({company.jobs.length})
        </h2>
        {company.jobs.map((job) => (
          <JobCard key={job.id} job={job} />
        ))}
      </div>
    </div>
  );
}
