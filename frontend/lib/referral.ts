const KEY = "tsa_ref";
const TS_KEY = "tsa_ref_ts";
const TTL_MS = 30 * 24 * 60 * 60 * 1000;

export function captureRef(code: string | null | undefined) {
  if (typeof window === "undefined") return;
  if (!code) return;
  const clean = code.trim().toUpperCase();
  if (!clean) return;
  try {
    window.localStorage.setItem(KEY, clean);
    window.localStorage.setItem(TS_KEY, String(Date.now()));
  } catch {}
}

export function readRef(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const code = window.localStorage.getItem(KEY);
    const ts = Number(window.localStorage.getItem(TS_KEY) ?? 0);
    if (!code) return null;
    if (Date.now() - ts > TTL_MS) {
      window.localStorage.removeItem(KEY);
      window.localStorage.removeItem(TS_KEY);
      return null;
    }
    return code;
  } catch {
    return null;
  }
}

export function clearRef() {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(KEY);
    window.localStorage.removeItem(TS_KEY);
  } catch {}
}
