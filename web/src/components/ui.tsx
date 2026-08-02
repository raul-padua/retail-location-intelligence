"use client";

/**
 * Presentational primitives shared across the panels.
 *
 * Deliberately unopinionated about data: nothing in here reads the workflow, so a panel
 * can be tested by handing it props without standing up a session.
 */

import clsx from "clsx";
import type { ReactNode } from "react";

export type Tone = "neutral" | "positive" | "warning" | "negative" | "accent";

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "bg-slate-100 text-slate-700 ring-slate-200",
  positive: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  warning: "bg-amber-50 text-amber-900 ring-amber-200",
  negative: "bg-rose-50 text-rose-800 ring-rose-200",
  accent: "bg-blue-50 text-blue-800 ring-blue-200",
};

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        TONE_CLASSES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Banner({
  tone = "neutral",
  title,
  children,
}: {
  tone?: Tone;
  title?: string;
  children: ReactNode;
}) {
  return (
    <div
      role={tone === "negative" ? "alert" : "status"}
      className={clsx(
        "rounded-lg px-4 py-3 text-sm ring-1 ring-inset",
        TONE_CLASSES[tone],
      )}
    >
      {title ? <p className="font-semibold">{title}</p> : null}
      <div className={clsx(title && "mt-1")}>{children}</div>
    </div>
  );
}

export function Card({
  title,
  description,
  actions,
  children,
  className,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={clsx(
        "rounded-xl border border-slate-200 bg-white shadow-sm",
        className,
      )}
    >
      {(title || actions) && (
        <header className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
          <div>
            {title ? (
              <h2 className="text-base font-semibold text-slate-900">{title}</h2>
            ) : null}
            {description ? (
              <p className="mt-1 text-sm text-slate-500">{description}</p>
            ) : null}
          </div>
          {actions ? <div className="shrink-0">{actions}</div> : null}
        </header>
      )}
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

export function Metric({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/60 px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p
        className={clsx(
          "mt-1 text-2xl font-semibold tabular-nums",
          tone === "positive" && "text-emerald-700",
          tone === "negative" && "text-rose-700",
          !tone && "text-slate-900",
        )}
      >
        {value}
      </p>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}

export function Button({
  children,
  onClick,
  variant = "secondary",
  disabled,
  type = "button",
  title,
  className,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  disabled?: boolean;
  type?: "button" | "submit";
  title?: string;
  className?: string;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition",
        "disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" &&
          "bg-blue-600 text-white shadow-sm hover:bg-blue-700 disabled:hover:bg-blue-600",
        variant === "secondary" &&
          "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50",
        variant === "ghost" && "text-slate-600 hover:bg-slate-100",
        variant === "danger" &&
          "border border-rose-300 bg-white text-rose-700 hover:bg-rose-50",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function Field({
  label,
  hint,
  children,
  htmlFor,
}: {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
  htmlFor?: string;
}) {
  return (
    <div className="space-y-1.5">
      <label
        htmlFor={htmlFor}
        className="block text-sm font-medium text-slate-700"
      >
        {label}
      </label>
      {children}
      {hint ? <p className="text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}

export function Table({
  columns,
  children,
  dense,
}: {
  columns: ReactNode[];
  children: ReactNode;
  dense?: boolean;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left">
            {columns.map((column, index) => (
              <th
                key={index}
                scope="col"
                className={clsx(
                  "whitespace-nowrap font-medium text-slate-500",
                  dense ? "px-2 py-1.5 text-xs" : "px-3 py-2",
                )}
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">{children}</tbody>
      </table>
    </div>
  );
}

export function Cell({
  children,
  numeric,
  className,
  colSpan,
}: {
  children: ReactNode;
  numeric?: boolean;
  className?: string;
  colSpan?: number;
}) {
  return (
    <td
      colSpan={colSpan}
      className={clsx(
        "px-3 py-2 align-top text-slate-700",
        numeric && "text-right tabular-nums",
        className,
      )}
    >
      {children}
    </td>
  );
}

export function Disclosure({
  summary,
  children,
  defaultOpen,
}: {
  summary: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details
      open={defaultOpen}
      className="group rounded-lg border border-slate-200 bg-white"
    >
      <summary className="cursor-pointer list-none px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50">
        <span className="mr-2 inline-block transition group-open:rotate-90">
          ›
        </span>
        {summary}
      </summary>
      <div className="border-t border-slate-100 px-4 py-3">{children}</div>
    </details>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-lg border border-dashed border-slate-300 px-4 py-6 text-center text-sm text-slate-500">
      {children}
    </p>
  );
}

export function Json({ value }: { value: unknown }) {
  return (
    <pre className="max-h-80 overflow-auto rounded-lg bg-slate-900 px-3 py-2 text-xs leading-relaxed text-slate-100">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

/**
 * Renders generated prose: paragraphs on blank lines, and `**bold**` as bold.
 *
 * The narrator and the assistant both emit those two constructs and nothing else. A
 * markdown library would handle them, and would also handle links, images, and raw HTML -
 * which is a poor trade when some of this text originates from a language model. Two
 * constructs, no parser, no injection surface.
 */
export function Prose({ text, className }: { text: string; className?: string }) {
  return (
    <div className={clsx("space-y-3 text-sm leading-relaxed text-slate-700", className)}>
      {text
        .split(/\n\s*\n/)
        .map((paragraph) => paragraph.trim())
        .filter(Boolean)
        .map((paragraph, index) => (
          <p key={index} className="whitespace-pre-wrap">
            {paragraph.split(/(\*\*[^*]+\*\*)/g).map((part, partIndex) =>
              part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
                <strong key={partIndex} className="font-semibold text-slate-900">
                  {part.slice(2, -2)}
                </strong>
              ) : (
                part
              ),
            )}
          </p>
        ))}
    </div>
  );
}

export function SectionHeading({
  children,
  hint,
}: {
  children: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div className="mb-3">
      <h3 className="text-sm font-semibold text-slate-900">{children}</h3>
      {hint ? <p className="mt-0.5 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}
