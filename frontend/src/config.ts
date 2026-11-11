const positive = (name: string, fallback: number) => {
  const n = Number(import.meta.env[name]);
  return Number.isFinite(n) && n > 0 ? n : fallback;
};
export const config = {
  baseUrl: (
    import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
  ).replace(/\/$/, ""),
  pollInterval: positive("VITE_POLL_INTERVAL_MS", 2500),
  chatTimeout: positive("VITE_CHAT_TIMEOUT_MS", 240000),
  requestTimeout: positive("VITE_REQUEST_TIMEOUT_MS", 15000),
  maxJD: positive("VITE_MAX_JD_CHARS", 100000),
  maxMessage: positive("VITE_MAX_MESSAGE_CHARS", 4000),
  demo: import.meta.env.VITE_DEMO === "true",
};
