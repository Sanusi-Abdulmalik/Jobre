import Link from "next/link";
import { MapPin, Building2, Clock, ExternalLink, GitMerge, DollarSign } from "lucide-react";
import { JobSummary, formatSalary, formatDateShort, formatEnumLabel } from "@/lib/api";
import { StatusBadge } from "./StatusBadge";

export function JobCard({ job }: { job: JobSummary }) {
  const salary = formatSalary(job);
  const locationDisplay =
    job.location_raw ||
    [job.city, job.region, job.country].filter(Boolean).join(", ") ||
    "Location not specified";

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 hover:border-blue-400 hover:shadow-sm transition-all">
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 mb-1.5">
            <Link
              href={`/companies/${job.company_id}`}
              className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-blue-700 hover:underline"
            >
              <Building2 className="w-3.5 h-3.5" />
              {job.company_name}
            </Link>
            {job.department && (
              <span className="text-xs text-slate-400">• {job.department}</span>
            )}
            {job.source_count > 1 && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-200">
                <GitMerge className="w-3 h-3" />
                Deduplicated ({job.source_count} sources)
              </span>
            )}
          </div>

          <Link
            href={`/jobs/${job.id}`}
            className="block text-lg font-semibold text-slate-900 hover:text-blue-600 transition-colors"
          >
            {job.title}
          </Link>

          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm text-slate-600">
            <span className="inline-flex items-center gap-1">
              <MapPin className="w-4 h-4 text-slate-400 shrink-0" />
              {locationDisplay}
            </span>
            {salary && (
              <span className="inline-flex items-center gap-1 font-medium text-emerald-700">
                <DollarSign className="w-4 h-4 shrink-0" />
                {salary}
              </span>
            )}
            <span className="inline-flex items-center gap-1 text-slate-500 text-xs">
              <Clock className="w-3.5 h-3.5" />
              {job.original_posted_at
                ? `Posted ${formatDateShort(job.original_posted_at)}`
                : `Indexed ${formatDateShort(job.first_seen_at)}`}
            </span>
          </div>
        </div>

        <div className="flex sm:flex-col items-start sm:items-end justify-between gap-2 shrink-0">
          <div className="flex flex-wrap items-center gap-1.5">
            {job.workplace_type && job.workplace_type !== "UNKNOWN" && (
              <StatusBadge status={job.workplace_type} />
            )}
            {job.employment_type && job.employment_type !== "UNKNOWN" && (
              <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200">
                {formatEnumLabel(job.employment_type)}
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {(job.platform_names && job.platform_names.length > 0
              ? job.platform_names
              : job.platforms
            ).map((p) => (
              <span
                key={p}
                className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-50 text-slate-600 border border-slate-200"
              >
                {p}
              </span>
            ))}
          </div>
        </div>
      </div>

      {job.snippet && (
        <p className="mt-3 text-sm text-slate-600 line-clamp-2">{job.snippet}</p>
      )}

      <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
        <Link
          href={`/jobs/${job.id}`}
          className="font-semibold text-blue-600 hover:text-blue-800"
        >
          View normalized record & provenance →
        </Link>
        <a
          href={job.primary_application_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 font-medium text-slate-700 hover:text-slate-900"
        >
          Apply directly <ExternalLink className="w-3.5 h-3.5" />
        </a>
      </div>
    </div>
  );
}
