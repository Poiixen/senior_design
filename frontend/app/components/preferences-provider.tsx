import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { DEFAULT_PREFERENCES, PREFERENCES_KEY, readPreferences, resolveAppearance, validatePreferences, writePreferences, type Preferences } from "~/lib/preferences";

const PreferencesContext = createContext({ preferences: DEFAULT_PREFERENCES, update: (_value: Partial<Preferences>) => {}, reset: () => {} });
export const usePreferences = () => useContext(PreferencesContext);

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState(DEFAULT_PREFERENCES);
  const current = useRef(preferences);
  const [ready, setReady] = useState(false);
  const [system, setSystem] = useState({ dark: false, reduced: false });
  useEffect(() => {
    let stored = DEFAULT_PREFERENCES;
    try { stored = readPreferences(window.localStorage); } catch { /* Storage can be blocked. */ }
    current.current = stored; setPreferences(stored); setReady(true);
    const dark = matchMedia("(prefers-color-scheme: dark)");
    const reduced = matchMedia("(prefers-reduced-motion: reduce)");
    const syncSystem = () => setSystem({ dark: dark.matches, reduced: reduced.matches });
    const syncStorage = (event: StorageEvent) => {
      if (event.key !== PREFERENCES_KEY && event.key !== null) return;
      let next = DEFAULT_PREFERENCES;
      try { next = readPreferences(window.localStorage); } catch { /* Keep safe defaults. */ }
      current.current = next; setPreferences(next);
    };
    syncSystem(); dark.addEventListener("change", syncSystem); reduced.addEventListener("change", syncSystem);
    window.addEventListener("storage", syncStorage);
    return () => { dark.removeEventListener("change", syncSystem); reduced.removeEventListener("change", syncSystem); window.removeEventListener("storage", syncStorage); };
  }, []);
  useEffect(() => {
    if (!ready) return;
    const resolved = resolveAppearance(preferences, system.dark, system.reduced);
    document.documentElement.dataset.theme = resolved.theme;
    document.documentElement.dataset.accent = preferences.accent;
    document.documentElement.dataset.motion = resolved.motion;
    document.documentElement.dataset.density = preferences.density;
  }, [preferences, system, ready]);
  const update = (value: Partial<Preferences>) => {
    const next = validatePreferences({ ...current.current, ...value });
    current.current = next; setPreferences(next);
    try { writePreferences(window.localStorage, next); } catch { /* Still applies for this session. */ }
  };
  return <PreferencesContext.Provider value={{ preferences, update, reset: () => update(DEFAULT_PREFERENCES) }}>{children}</PreferencesContext.Provider>;
}
