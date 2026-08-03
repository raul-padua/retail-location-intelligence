"use client";

/**
 * Horizontal split with a drag handle. Width is presentation chrome only — it does not
 * change workflow or analytical state. Persists the fraction in sessionStorage when a
 * storage key is provided.
 */

import {
  useCallback,
  useId,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";

import clsx from "clsx";

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function ResizableSplit({
  left,
  right,
  storageKey,
  defaultFraction = 0.58,
  minLeftPx = 280,
  minRightPx = 280,
  className,
}: {
  left: ReactNode;
  right: ReactNode;
  storageKey?: string;
  defaultFraction?: number;
  minLeftPx?: number;
  minRightPx?: number;
  className?: string;
}) {
  const groupId = useId();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [fraction, setFraction] = useState(() => {
    if (!storageKey || typeof window === "undefined") return defaultFraction;
    const raw = window.sessionStorage.getItem(storageKey);
    if (!raw) return defaultFraction;
    const parsed = Number.parseFloat(raw);
    return Number.isFinite(parsed) ? clamp(parsed, 0.2, 0.8) : defaultFraction;
  });
  const [dragging, setDragging] = useState(false);

  const persist = useCallback(
    (value: number) => {
      if (!storageKey || typeof window === "undefined") return;
      window.sessionStorage.setItem(storageKey, String(value));
    },
    [storageKey],
  );

  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      const container = containerRef.current;
      if (!container) return;
      const handle = event.currentTarget;
      handle.setPointerCapture(event.pointerId);
      setDragging(true);

      const onMove = (moveEvent: PointerEvent) => {
        const rect = container.getBoundingClientRect();
        if (rect.width <= 0) return;
        const leftPx = moveEvent.clientX - rect.left;
        const maxLeft = rect.width - minRightPx;
        const clampedLeft = clamp(leftPx, minLeftPx, Math.max(minLeftPx, maxLeft));
        const next = clamp(clampedLeft / rect.width, 0.2, 0.8);
        setFraction(next);
      };

      const onUp = (upEvent: PointerEvent) => {
        handle.releasePointerCapture(upEvent.pointerId);
        handle.removeEventListener("pointermove", onMove);
        handle.removeEventListener("pointerup", onUp);
        handle.removeEventListener("pointercancel", onUp);
        setDragging(false);
        const rect = container.getBoundingClientRect();
        if (rect.width > 0) {
          const leftPx = upEvent.clientX - rect.left;
          const maxLeft = rect.width - minRightPx;
          const clampedLeft = clamp(leftPx, minLeftPx, Math.max(minLeftPx, maxLeft));
          persist(clamp(clampedLeft / rect.width, 0.2, 0.8));
        }
      };

      handle.addEventListener("pointermove", onMove);
      handle.addEventListener("pointerup", onUp);
      handle.addEventListener("pointercancel", onUp);
    },
    [minLeftPx, minRightPx, persist],
  );

  return (
    <div
      ref={containerRef}
      className={clsx(
        "flex min-h-0 min-w-0 flex-1 flex-col lg:flex-row",
        dragging ? "select-none" : null,
        className,
      )}
    >
      <div
        className="flex min-h-0 min-w-0 flex-1 flex-col lg:min-h-0"
        style={{ flexGrow: fraction * 1000, flexBasis: 0 }}
      >
        {left}
      </div>

      <div
        role="separator"
        aria-orientation="vertical"
        aria-controls={groupId}
        aria-valuenow={Math.round(fraction * 100)}
        aria-valuemin={20}
        aria-valuemax={80}
        aria-label="Resize panels"
        tabIndex={0}
        onPointerDown={onPointerDown}
        onKeyDown={(event) => {
          const step = event.shiftKey ? 0.05 : 0.02;
          if (event.key === "ArrowLeft") {
            event.preventDefault();
            setFraction((value) => {
              const next = clamp(value - step, 0.2, 0.8);
              persist(next);
              return next;
            });
          } else if (event.key === "ArrowRight") {
            event.preventDefault();
            setFraction((value) => {
              const next = clamp(value + step, 0.2, 0.8);
              persist(next);
              return next;
            });
          }
        }}
        className={clsx(
          "group relative z-10 hidden shrink-0 cursor-col-resize lg:block",
          "w-1.5 bg-slate-200/80 hover:bg-blue-400/70",
          dragging ? "bg-blue-500" : null,
        )}
      >
        <div className="absolute inset-y-0 -left-1 -right-1" />
        <div className="pointer-events-none absolute left-1/2 top-1/2 h-10 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-400 group-hover:bg-blue-600" />
      </div>

      <div
        id={groupId}
        className="flex min-h-0 min-w-0 flex-col lg:min-h-0"
        style={{ flexGrow: (1 - fraction) * 1000, flexBasis: 0 }}
      >
        {right}
      </div>
    </div>
  );
}
