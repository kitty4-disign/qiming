/**
 * ThemeScript - Initializes theme from localStorage before React hydration
 * This prevents the flash of wrong theme on page load.
 *
 * Must be a Server Component: in Next.js / React 19, <script> tags rendered
 * by Client Components are inert on the client. Rendering it from the server
 * inlines the snippet into the SSR HTML so the browser executes it before
 * hydration.
 */
export default function ThemeScript() {
  const themeScript = `
    (function() {
      try {
        var stored = localStorage.getItem('deeptutor-theme');

        // Retired themes migrate into the warm family: the old pure-white
        // "snow" default → Light (:root), the purple "glass" → Dark.
        if (stored === 'snow') { stored = 'light'; localStorage.setItem('deeptutor-theme', 'light'); }
        if (stored === 'glass') { stored = 'dark'; localStorage.setItem('deeptutor-theme', 'dark'); }

        document.documentElement.classList.remove('dark', 'theme-glass', 'theme-snow');

        if (stored === 'dark') {
          document.documentElement.classList.add('dark');
        } else if (stored === 'light') {
          // Light is the bare :root palette — no class needed.
        } else {
          // No stored preference: warm Light for light systems, Dark for
          // prefers-color-scheme: dark.
          if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
            document.documentElement.classList.add('dark');
            localStorage.setItem('deeptutor-theme', 'dark');
          } else {
            localStorage.setItem('deeptutor-theme', 'light');
          }
        }
      } catch (e) {
        /* localStorage may be disabled */
      }
    })();
  `;

  return (
    <script
      dangerouslySetInnerHTML={{ __html: themeScript }}
      suppressHydrationWarning
    />
  );
}
