/**
 * Theme persistence utilities
 * Handles light/dark theme with localStorage fallback and system preference detection
 */

// The app ships a single warm "Claude" family with two modes: Light (:root)
// and Dark. "glass"/"snow" are retired ids kept in the union only so stored
// preferences from older builds still type-check; they are migrated to
// light/dark on read (see getStoredTheme).
export type Theme = "light" | "dark" | "glass" | "snow";

export const THEME_STORAGE_KEY = "deeptutor-theme";

type ThemeChangeListener = (theme: Theme) => void;
const themeListeners = new Set<ThemeChangeListener>();

/**
 * Subscribe to theme changes
 */
export function subscribeToThemeChanges(
  listener: ThemeChangeListener,
): () => void {
  themeListeners.add(listener);
  return () => themeListeners.delete(listener);
}

/**
 * Notify all listeners of theme change
 */
function notifyThemeChange(theme: Theme): void {
  themeListeners.forEach((listener) => listener(theme));
}

/**
 * Get the stored theme from localStorage
 */
export function getStoredTheme(): Theme | null {
  if (typeof window === "undefined") return null;

  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    // Migrate retired ids into the warm family.
    if (stored === "snow") return "light";
    if (stored === "glass") return "dark";
    if (stored === "light" || stored === "dark") {
      return stored;
    }
  } catch (e) {
    // Silently fail - localStorage may be disabled
  }

  return null;
}

/**
 * Save theme to localStorage
 */
export function saveThemeToStorage(theme: Theme): boolean {
  if (typeof window === "undefined") return false;

  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
    return true;
  } catch (e) {
    // Silently fail - localStorage may be disabled or full
    return false;
  }
}

/**
 * Get system preference for theme.
 * Light systems get "light" (the warm Claude default); dark systems get
 * "dark". Must stay in sync with the inline ThemeScript fallback.
 */
export function getSystemTheme(): Theme {
  if (typeof window === "undefined") return "light";

  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

/**
 * Apply theme to document
 */
export function applyThemeToDocument(theme: Theme): void {
  if (typeof document === "undefined") return;

  const html = document.documentElement;

  html.classList.remove("dark", "theme-glass", "theme-snow");

  // "glass"/"snow" are retired; treat any dark-family id as Dark, everything
  // else as the bare :root Light palette.
  if (theme === "dark" || theme === "glass") {
    html.classList.add("dark");
  }
}

/**
 * Initialize theme on app startup
 * Priority: localStorage > system preference (light on light systems, dark on dark)
 */
export function initializeTheme(): Theme {
  // Check localStorage first
  const stored = getStoredTheme();
  if (stored) {
    applyThemeToDocument(stored);
    return stored;
  }

  // Fall back to system preference
  const systemTheme = getSystemTheme();
  applyThemeToDocument(systemTheme);
  saveThemeToStorage(systemTheme);
  return systemTheme;
}

/**
 * Set theme and persist it
 */
export function setTheme(theme: Theme): void {
  applyThemeToDocument(theme);
  saveThemeToStorage(theme);
  notifyThemeChange(theme);
}
