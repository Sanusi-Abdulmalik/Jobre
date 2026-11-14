import Link from "next/link";

export function Footer() {
  return (
    <footer className="bg-white border-t border-slate-200 mt-16">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-slate-500">
        <div>
          <span className="font-semibold text-slate-900">Jobre</span> — Universal Job Discovery, Aggregation & Monitoring Platform.
        </div>
        <div className="flex items-center gap-5">
          <Link href="/jobs" className="hover:text-slate-900">
            Job Index
          </Link>
          <Link href="/companies" className="hover:text-slate-900">
            Employers
          </Link>
          <Link href="/about" className="hover:text-slate-900">
            78-Platform Matrix
          </Link>
          <a
            href="/docs"
            target="_blank"
            rel="noreferrer"
            className="hover:text-slate-900"
          >
            OpenAPI Docs
          </a>
          <Link href="/admin" className="hover:text-slate-900">
            Admin
          </Link>
        </div>
      </div>
    </footer>
  );
}
