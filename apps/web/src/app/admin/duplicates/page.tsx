"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { GitMerge, Check, X, Undo2, ExternalLink } from "lucide-react";
import { adminFetch } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

interface DuplicateCandidateItem {
  id: string;
  candidate_job_id: string;
  candidate_title: string;
  source_name: string | null;
  platform_name: string | null;
  source_job_url: string;
  similarity_score: number;
  matching_signals: Record<string, unknown>;
  review_status: string;
}

interface DuplicateGroupItem {
  id: string;
  canonical_job_id: string;
  canonical_title: string;
  company_name: string;
  canonical_location: string | null;
  source_count: number;
  confidence: number;
  resolution_status: string;
  created_at: string;
  candidates: DuplicateCandidateItem[];
}

export default function AdminDuplicatesPage() {
  const [groups, setGroups] = useState<DuplicateGroupItem[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () => {
    adminFetch<{ items: DuplicateGroupItem[] }>("/api/v1/admin/duplicates")
      .then((res) => setGroups(res.items))
      .catch(console.error);
  };

  useEffect(() => {
    load();
  }, []);

  const act = async (groupId: string, action: "approve" | "reject" | "unmerge") => {
    setMsg(null);
    try {
      const res = await adminFetch<Record<string, unknown>>(
        `/api/v1/admin/duplicates/${groupId}/${action}`,
        { method: "POST" }
      );
      setMsg(`Action '${action}' succeeded: ${JSON.stringify(res)}`);
      load();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Action failed");
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl border border-slate-200 p-6">
        <h1 className="text-2xl font-bold text-slate-900">
          Cross-Source Duplicate Review Queue ({groups.length})
        </h1>
        <p className="text-sm text-slate-600">
          Inspect multi-signal deduplication matches across independent job boards
          and employer ATS portals, approve/reject candidate merges, or unmerge
          canonical groups.
        </p>
      </div>

      {msg && (
        <div className="bg-blue-50 border border-blue-200 text-blue-900 rounded-xl p-3.5 text-xs font-mono">
          {msg}
        </div>
      )}

      {groups.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-10 text-center text-sm text-slate-500">
          No duplicate groups recorded yet.
        </div>
      ) : (
        <div className="space-y-4">
          {groups.map((g) => (
            <div
              key={g.id}
              className="bg-white rounded-2xl border border-slate-200 p-6 space-y-4"
            >
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <StatusBadge status={g.resolution_status} />
                    <span className="text-xs font-mono text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded">
                      Confidence: {(g.confidence * 100).toFixed(0)}%
                    </span>
                    <span className="text-xs text-slate-500">
                      {g.source_count} linked sources
                    </span>
                  </div>
                  <Link
                    href={`/jobs/${g.canonical_job_id}`}
                    className="text-lg font-bold text-slate-900 hover:text-blue-600"
                  >
                    {g.canonical_title}
                  </Link>
                  <div className="text-xs text-slate-600 mt-0.5">
                    {g.company_name} • {g.canonical_location || "Remote / Unspecified"}
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  {g.resolution_status === "PENDING_REVIEW" && (
                    <>
                      <button
                        onClick={() => act(g.id, "approve")}
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs font-semibold"
                      >
                        <Check className="w-3.5 h-3.5" />
                        Approve Merge
                      </button>
                      <button
                        onClick={() => act(g.id, "reject")}
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-rose-600 text-white text-xs font-semibold"
                      >
                        <X className="w-3.5 h-3.5" />
                        Reject
                      </button>
                    </>
                  )}
                  {(g.resolution_status === "AUTO_MERGED" ||
                    g.resolution_status === "APPROVED") && (
                    <button
                      onClick={() => act(g.id, "unmerge")}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold"
                    >
                      <Undo2 className="w-3.5 h-3.5" />
                      Unmerge Group
                    </button>
                  )}
                </div>
              </div>

              <div className="space-y-2 pt-3 border-t border-slate-100">
                {g.candidates.map((c) => (
                  <div
                    key={c.id}
                    className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xs space-y-2"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="font-semibold text-slate-800 flex items-center gap-1.5">
                        <GitMerge className="w-3.5 h-3.5 text-indigo-600" />
                        {c.source_name || "External Source"} ({c.platform_name})
                      </div>
                      <a
                        href={c.source_job_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-blue-600 hover:underline"
                      >
                        Secondary Listing <ExternalLink className="w-3 h-3" />
                      </a>
                    </div>
                    <pre className="text-[11px] text-slate-600 overflow-x-auto">
                      {JSON.stringify(c.matching_signals, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
