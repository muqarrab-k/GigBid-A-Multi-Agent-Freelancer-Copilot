import type { ButtonHTMLAttributes, ReactNode } from "react";

export function Page({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="mx-auto w-full max-w-6xl px-4 py-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">{title}</h1>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function Card({ title, children, className = "" }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-slate-200 bg-white p-4 shadow-sm ${className}`}>
      {title && <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>}
      {children}
    </div>
  );
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return <p role="status" className="py-6 text-slate-500">{what}…</p>;
}

export function ErrorBox({ error }: { error: unknown }) {
  const text = error instanceof Error ? error.message : String(error);
  return <p role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-red-800">{text}</p>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-md border border-dashed border-slate-300 p-6 text-center text-slate-500">{children}</p>;
}

const TONES: Record<string, string> = {
  red: "bg-red-100 text-red-800",
  amber: "bg-amber-100 text-amber-800",
  green: "bg-green-100 text-green-800",
  slate: "bg-slate-100 text-slate-700",
  indigo: "bg-indigo-100 text-indigo-800",
};

export function Badge({ tone = "slate", children }: { tone?: string; children: ReactNode }) {
  return <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}>{children}</span>;
}

export function actionTone(action?: string | null): string {
  return action === "bid" ? "green" : action === "watch" ? "amber" : action === "skip" ? "red" : "slate";
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { kind?: "primary" | "secondary" | "danger" };

export function Button({ kind = "primary", className = "", ...props }: ButtonProps) {
  const look = {
    primary: "bg-indigo-600 text-white hover:bg-indigo-700",
    secondary: "border border-slate-300 bg-white hover:bg-slate-50",
    danger: "bg-red-600 text-white hover:bg-red-700",
  }[kind];
  return <button className={`rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${look} ${className}`} {...props} />;
}

export function money(value?: number | null, billing?: string | null): string {
  if (value === null || value === undefined) return "—";
  return `$${Math.round(value)}${billing === "hourly" ? "/h" : ""}`;
}

export function Field({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium">{label}</label>
      {children}
    </div>
  );
}

export const inputClass = "w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm";
