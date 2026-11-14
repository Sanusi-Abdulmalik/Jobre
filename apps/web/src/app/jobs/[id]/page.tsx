"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Building2,
  MapPin,
  ExternalLink,
  GitMerge,
  Clock,
  Hash,
  DollarSign,
} from "lucide-react";
import {
  apiGet,
  JobDetail,
  formatSalary,
  formatDateTime,
  formatEnumLabel,
} from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function JobDetailPage({ params }: { params: { id: string } }) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<JobDetail>(`/api/v1/jobs/${params.id}`)
      .then(setJob)
      .catch((err) => setError(err instanceof Error ? err.message : "Not found"))
      .finally(() => setLoading(false));
  }, [params.id]);

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-12">
        <div className="h-64 rounded-2xl bg-white border border-slate-200 animate-pulse" />
      </div>
    );
  }

  if (error || !job) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-12">
        <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center">
          <h1 className="text-xl font-bold text-slate-900">Job Not Found</h1>
          <p className="mt-2 text-sm text-slate-600">{error}</p>
          <Link
            href="/jobs"
            className="inline-block mt-4 px-4 py-2 rounded-lg bg-slate-900 text-white text-sm font-semibold"
          >
            Back to Search
          </Link>
        </div>
      </div>
    );
  }

  const salary = formatSalary(job);

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <Link
        href="/jobs"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Job Search
      </Link>

      <div className="bg-white rounded-2xl border border-slate-200 p-6 sm:p-8 shadow-2xs">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <StatusBadge status={job.status} />
              <StatusBadge status={job.workplace_type} />
              <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200">
                {formatEnumLabel(job.employment_type)}
              </span>
              {job.source_count > 1 && (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-200">
                  <GitMerge className="w-3.5 h-3.5" />
                  Verified across {job.source_count} sources
                </span>
              )}
            </div>

            <h1 className="text-2xl sm:text-3xl font-bold text-slate-900">
              {job.title}
            </h1>

            <div className="mt-3 flex flex-wrap items-center gap-4 text-sm text-slate-600">
              <Link
                href={`/companies/${job.company_id}`}
                className="inline-flex items-center gap-1.5 font-semibold text-blue-700 hover:underline"
              >
                <Building2 className="w-4 h-4" />
                {job.company_name}
              </Link>
              <span className="inline-flex items-center gap-1.5">
                <MapPin className="w-4 h-4 text-slate-400" />
                {job.location_raw ||
                  [job.city, job.region, job.country].filter(Boolean).join(", ") ||
                  "Unspecified"}
              </span>
              {job.department && <span>Dept: {job.department}</span>}
            </div>
          </div>

          <div className="flex flex-col sm:flex-row md:flex-col gap-2 shrink-0">
            <a
              href={job.primary_application_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold text-sm shadow-xs transition-colors"
            >
              Apply on Source <ExternalLink className="w-4 h-4" />
            </a>
            <a
              href={job.primary_source_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl border border-slate-200 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              View Original Listing <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
        </div>

        <div className="mt-6 pt-6 border-t border-slate-100 grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
          <div>
            <div className="text-slate-400 uppercase font-semibold">Compensation</div>
            <div className="mt-1 font-semibold text-slate-900 flex items-center gap-1">
              <DollarSign className="w-3.5 h-3.5 text-emerald-600" />
              {salary || "Not disclosed by source"}
            </div>
          </div>
          <div>
            <div className="text-slate-400 uppercase font-semibold">
              Original Posted
            </div>
            <div className="mt-1 font-medium text-slate-800">
              {formatDateTime(job.original_posted_at)}
            </div>
          </div>
          <div>
            <div className="text-slate-400 uppercase font-semibold">First Indexed</div>
            <div className="mt-1 font-medium text-slate-800">
              {formatDateTime(job.first_seen_at)}
            </div>
          </div>
          <div>
            <div className="text-slate-400 uppercase font-semibold">
              Last Verified Active
            </div>
            <div className="mt-1 font-medium text-slate-800">
              {formatDateTime(job.last_seen_at)}
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-6 sm:p-8">
        <h2 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
          <GitMerge className="w-5 h-5 text-indigo-600" />
          Source Provenance ({job.sources.length})
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase text-slate-500">
                <th className="py-2.5 pr-4">Source</th>
                <th className="py-2.5 pr-4">Platform</th>
                <th className="py-2.5 pr-4">External ID</th>
                <th className="py-2.5 pr-4">Active on Source</th>
                <th className="py-2.5 pr-4">Last Seen</th>
                <th className="py-2.5">Links</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {job.sources.map((s) => (
                <tr key={`${s.source_id}-${s.external_job_id}`}>
                  <td className="py-3 pr-4 font-medium text-slate-900">
                    {s.source_name}
                  </td>
                  <td className="py-3 pr-4 font-mono text-xs text-slate-600">
                    {s.platform_name || s.platform_key || "—"}
                  </td>
                  <td className="py-3 pr-4 font-mono text-xs text-slate-500">
                    {s.external_job_id}
                  </td>
                  <td className="py-3 pr-4">
                    <StatusBadge
                      status={s.is_active_on_source ? "ACTIVE" : "CLOSED"}
                    />
                  </td>
                  <td className="py-3 pr-4 text-xs text-slate-500">
                    {formatDateTime(s.last_seen_at)}
                  </td>
                  <td className="py-3">
                    <a
                      href={s.source_job_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:underline"
                    >
                      Listing <ExternalLink className="w-3 h-3" />
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-6 sm:p-8">
        <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-100">
          <h2 className="text-lg font-bold text-slate-900">Job Description</h2>
          <span className="inline-flex items-center gap-1 text-xs font-mono text-slate-400">
            <Hash className="w-3.5 h-3.5" />
            {job.content_hash.slice(0, 12)}
          </span>
        </div>
        {job.description_text ? (
          <div className="prose-job whitespace-pre-line text-sm text-slate-700 leading-relaxed">
            {job.description_text}
          </div>
        ) : (
          <p className="text-sm text-slate-500 italic">
            Full description available on the primary source posting.
          </p>
        )}
      </div>

      {job.changes && job.changes.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-200 p-6 sm:p-8">
          <h2 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
            <Clock className="w-5 h-5 text-slate-500" />
            Lifecycle & Field Change History
          </h2>
          <div className="space-y-3">
            {job.changes.map((ch) => (
              <div
                key={ch.id}
                className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xs"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-semibold text-slate-900">
                    {ch.change_type}
                  </span>
                  <span className="text-slate-500">
                    {formatDateTime(ch.detected_at)}
                  </span>
                </div>
                <pre className="text-[11px] text-slate-600 overflow-x-auto">
                  {JSON.stringify(ch.changed_fields, null, 2)}
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
