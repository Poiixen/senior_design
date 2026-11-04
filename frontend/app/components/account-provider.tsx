import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import { ApiError, getCurrentUser, logoutUser, type AuthUser } from "~/lib/api";
import { ACTIVITY_SYNC_MS, SESSION_IDLE_MS } from "~/lib/session";

interface AccountState {
  user: AuthUser | null; loading: boolean; error: string; loggingOut: boolean;
  refresh: () => void; logout: () => Promise<void>;
}
const AccountContext = createContext<AccountState>({ user: null, loading: false, error: "", loggingOut: false, refresh: () => {}, logout: async () => {} });
export const useAccount = () => useContext(AccountContext);

export function AccountProvider({ children }: { children: ReactNode }) {
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [loggingOut, setLoggingOut] = useState(false);
  const [revision, setRevision] = useState(0);
  const generation = useRef(0);
  const currentLocation = useRef({ pathname, search });
  const activityChannel = useRef<BroadcastChannel | null>(null);
  useEffect(() => { currentLocation.current = { pathname, search }; }, [pathname, search]);
  useEffect(() => {
    let active = true;
    const requestGeneration = ++generation.current;
    const isCurrent = () => active && requestGeneration === generation.current;
    setLoading(true); setError("");
    getCurrentUser().then(value => { if (isCurrent()) setUser(value); }).catch(reason => {
      if (!isCurrent()) return;
      if (reason instanceof ApiError && reason.status === 401) setUser(null);
      else setError("Account information is temporarily unavailable.");
    }).finally(() => { if (isCurrent()) setLoading(false); });
    return () => { active = false; };
  }, [pathname, revision]);
  useEffect(() => {
    if (!user) return;
    const userId = user.id;
    let stopped = false;
    let expired = false;
    let lastActivity = Date.now();
    let lastSync = lastActivity;
    let lastBroadcast = 0;
    let syncing = false;
    let timeout: ReturnType<typeof setTimeout>;
    let channel: BroadcastChannel | null = null;
    try { channel = new BroadcastChannel("team-science.session-activity"); } catch { /* Each tab still enforces its own idle timer. */ }
    activityChannel.current = channel;
    const expire = (notifyOthers = true) => {
      if (expired || stopped) return;
      expired = true;
      generation.current += 1;
      clearTimeout(timeout);
      if (notifyOthers) {
        channel?.postMessage({ type: "expired", userId });
        void logoutUser().catch(() => { /* The server independently enforces session expiry. */ });
      }
      setUser(null); setLoading(false); setError("");
      const location = currentLocation.current;
      if (["/dashboard", "/upload", "/reports", "/settings"].includes(location.pathname) || (location.pathname.startsWith("/reports/") && location.pathname !== "/reports/sample")) {
        navigate(`/login?next=${encodeURIComponent(location.pathname + location.search)}`, { replace: true });
      }
    };
    const schedule = () => {
      clearTimeout(timeout);
      timeout = setTimeout(() => {
        if (Date.now() - lastActivity >= SESSION_IDLE_MS) expire();
        else schedule();
      }, Math.max(0, SESSION_IDLE_MS - (Date.now() - lastActivity)));
    };
    const activity = () => {
      if (expired || stopped || document.visibilityState === "hidden") return;
      const now = Date.now();
      if (now - lastActivity >= SESSION_IDLE_MS) { expire(); return; }
      lastActivity = now; schedule();
      if (now - lastBroadcast >= 1000) { channel?.postMessage({ type: "activity", userId, at: now }); lastBroadcast = now; }
      // Renew only in response to real interaction, never on an idle polling loop.
      if (!syncing && now - lastSync >= ACTIVITY_SYNC_MS) {
        syncing = true; lastSync = now;
        getCurrentUser().catch(reason => { if (!stopped && reason instanceof ApiError && reason.status === 401) expire(); }).finally(() => { syncing = false; });
      }
    };
    const checkIdle = () => { if (Date.now() - lastActivity >= SESSION_IDLE_MS) expire(); };
    if (channel) channel.onmessage = event => {
      const value = event.data;
      if (!value || value.userId !== userId || expired || stopped) return;
      if (value.type === "expired") { expire(false); return; }
      if (value.type === "activity" && typeof value.at === "number" && value.at > lastActivity && value.at <= Date.now() && Date.now() - value.at < SESSION_IDLE_MS) {
        lastActivity = value.at; schedule();
      }
    };
    const events = ["pointerdown", "pointermove", "keydown", "wheel", "touchstart"] as const;
    for (const event of events) window.addEventListener(event, activity, { passive: true });
    document.addEventListener("visibilitychange", checkIdle);
    window.addEventListener("focus", checkIdle);
    channel?.postMessage({ type: "activity", userId, at: lastActivity });
    schedule();
    return () => {
      stopped = true; clearTimeout(timeout); channel?.close(); activityChannel.current = null;
      for (const event of events) window.removeEventListener(event, activity);
      document.removeEventListener("visibilitychange", checkIdle); window.removeEventListener("focus", checkIdle);
    };
  }, [user?.id, navigate]);
  const logout = async () => {
    if (loggingOut) return;
    generation.current += 1;
    setLoading(false);
    setLoggingOut(true); setError("");
    try { await logoutUser(); activityChannel.current?.postMessage({ type: "expired", userId: user?.id }); setUser(null); navigate("/"); }
    catch { setError("Unable to log out. Please try again."); }
    finally { setLoggingOut(false); }
  };
  return <AccountContext.Provider value={{ user, loading, error, loggingOut, refresh: () => setRevision(value => value + 1), logout }}>{children}</AccountContext.Provider>;
}
