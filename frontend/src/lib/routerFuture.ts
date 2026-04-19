/** Opt into React Router v7 behaviors to silence upgrade warnings in dev/tests. */
export const ROUTER_FUTURE_FLAGS = {
  v7_startTransition: true,
  v7_relativeSplatPath: true,
} as const;
