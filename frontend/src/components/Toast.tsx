import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ToastErrorOptions = {
  action?: { label: string; onClick: () => void };
};

type ToastItem = {
  id: string;
  message: string;
  action?: { label: string; onClick: () => void };
};

type ToastContextValue = {
  pushError: (message: string, options?: ToastErrorOptions) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const v = useContext(ToastContext);
  if (!v) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return v;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const pushError = useCallback((message: string, options?: ToastErrorOptions) => {
    const id =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random()}`;
    setItems((prev) => [...prev, { id, message, action: options?.action }]);
    window.setTimeout(() => {
      setItems((prev) => prev.filter((t) => t.id !== id));
    }, 6000);
  }, []);

  const value = useMemo(() => ({ pushError }), [pushError]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed bottom-6 right-6 z-50 flex w-full max-w-sm flex-col gap-2"
        aria-live="polite"
      >
        {items.map((t) => (
          <div
            key={t.id}
            className="pointer-events-auto flex flex-col gap-2 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900 shadow-md sm:flex-row sm:items-center sm:justify-between"
            role="status"
          >
            <span className="min-w-0 flex-1">{t.message}</span>
            {t.action ? (
              <button
                type="button"
                className="shrink-0 rounded border border-red-300 bg-white px-3 py-1 text-xs font-medium text-red-900 hover:bg-red-100"
                onClick={() => {
                  t.action?.onClick();
                }}
              >
                {t.action.label}
              </button>
            ) : null}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
