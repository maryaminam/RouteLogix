import { useEffect, useState } from "react";

const STORAGE_KEY = "routelogix-theme";

const OPTIONS = [
  { value: "light", label: "Light", glyph: "☀" },
  { value: "system", label: "System", glyph: "◐" },
  { value: "dark", label: "Dark", glyph: "☾" },
];

function readStoredTheme() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

/**
 * "system" removes the attribute entirely so the prefers-color-scheme media
 * query governs; an explicit choice stamps data-theme, which wins in either
 * direction (including light-on-a-dark-OS).
 */
function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState(readStoredTheme);

  useEffect(() => {
    applyTheme(theme);
    try {
      if (theme === "system") localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Private browsing: the theme still applies for this session.
    }
  }, [theme]);

  return (
    <div className="theme-toggle" role="radiogroup" aria-label="Colour theme">
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={theme === option.value}
          className={`theme-toggle__option${theme === option.value ? " is-active" : ""}`}
          onClick={() => setTheme(option.value)}
          title={`${option.label} theme`}
        >
          <span aria-hidden="true">{option.glyph}</span>
          <span className="theme-toggle__label">{option.label}</span>
        </button>
      ))}
    </div>
  );
}
