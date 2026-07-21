import { useEffect, useRef, useState } from "react";
import { searchLocations } from "../api";
import { LOCATION_SEARCH_MIN_LENGTH } from "../tripValidation";

// Long enough that a normal typing burst produces one request rather than one
// per character. Both providers behind the endpoint are free instances.
const DEBOUNCE_MS = 350;

const STATUS = { IDLE: "idle", LOADING: "loading", READY: "ready", UNAVAILABLE: "unavailable" };

/**
 * Combobox over the /api/locations/search/ endpoint.
 *
 * Suggestions are an aid, not a constraint: the field stays free text, so a
 * place the provider doesn't know can still be typed and planned.
 */
export default function LocationAutocomplete({ name, label, hint, value, error, onValueChange, onBlur }) {
  const [suggestions, setSuggestions] = useState([]);
  const [status, setStatus] = useState(STATUS.IDLE);
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  // Picking a suggestion writes into `value`, which would otherwise look like
  // typing and immediately re-open the list with the chosen city in it.
  const skipNextLookup = useRef(false);

  const listboxId = `${name}-listbox`;
  const errorId = `${name}-error`;

  useEffect(() => {
    if (skipNextLookup.current) {
      skipNextLookup.current = false;
      return undefined;
    }

    const query = value.trim();
    if (query.length < LOCATION_SEARCH_MIN_LENGTH) {
      setSuggestions([]);
      setStatus(STATUS.IDLE);
      setIsOpen(false);
      return undefined;
    }

    const controller = new AbortController();
    setStatus(STATUS.LOADING);

    const timer = setTimeout(async () => {
      try {
        const results = await searchLocations(query, { signal: controller.signal });
        setSuggestions(results);
        setStatus(STATUS.READY);
        setActiveIndex(-1);
        setIsOpen(true);
      } catch (err) {
        // A superseded keystroke isn't a failure — the newer request owns the UI.
        if (err?.name === "AbortError") return;
        setSuggestions([]);
        setStatus(STATUS.UNAVAILABLE);
        setIsOpen(true);
      }
    }, DEBOUNCE_MS);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [value]);

  function choose(suggestion) {
    skipNextLookup.current = true;
    onValueChange(name, suggestion.value);
    setIsOpen(false);
    setActiveIndex(-1);
    setSuggestions([]);
    setStatus(STATUS.IDLE);
  }

  function handleKeyDown(event) {
    if (event.key === "Escape") {
      setIsOpen(false);
      setActiveIndex(-1);
      return;
    }

    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (!suggestions.length) return;
      event.preventDefault();
      setIsOpen(true);
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActiveIndex((previous) => {
        const next = previous + step;
        if (next < 0) return suggestions.length - 1;
        if (next >= suggestions.length) return 0;
        return next;
      });
      return;
    }

    // Enter only intercepts when an option is highlighted; otherwise it falls
    // through and submits the form as usual.
    if (event.key === "Enter" && isOpen && activeIndex >= 0 && suggestions[activeIndex]) {
      event.preventDefault();
      choose(suggestions[activeIndex]);
    }
  }

  function handleBlur(event) {
    setIsOpen(false);
    setActiveIndex(-1);
    onBlur?.(event);
  }

  const showPanel = isOpen && (status === STATUS.READY || status === STATUS.UNAVAILABLE);
  const activeId = activeIndex >= 0 ? `${name}-option-${activeIndex}` : undefined;

  return (
    <label className="autocomplete">
      {label}
      <div className="autocomplete__control">
        <input
          type="text"
          name={name}
          value={value}
          placeholder={hint}
          autoComplete="off"
          role="combobox"
          aria-expanded={showPanel}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={activeId}
          aria-invalid={error ? "true" : undefined}
          aria-describedby={error ? errorId : undefined}
          onChange={(event) => onValueChange(name, event.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={handleBlur}
          onFocus={() => suggestions.length && setIsOpen(true)}
        />
        {status === STATUS.LOADING && (
          <span className="autocomplete__spinner" aria-hidden="true" />
        )}

        {showPanel && (
          <ul className="autocomplete__panel" id={listboxId} role="listbox" aria-label={`${label} suggestions`}>
            {status === STATUS.UNAVAILABLE && (
              <li className="autocomplete__note" role="presentation">
                Suggestions are unavailable right now — type the city and state, like
                &quot;Denver, CO&quot;.
              </li>
            )}
            {status === STATUS.READY && suggestions.length === 0 && (
              <li className="autocomplete__note" role="presentation">
                No matches. You can still enter the location manually.
              </li>
            )}
            {suggestions.map((suggestion, index) => (
              <li
                key={`${suggestion.value}-${suggestion.lat}`}
                id={`${name}-option-${index}`}
                role="option"
                aria-selected={index === activeIndex}
                className={`autocomplete__option${index === activeIndex ? " is-active" : ""}`}
                // Keeps focus in the input so blur doesn't close the list before
                // the click lands.
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => choose(suggestion)}
              >
                <span className="autocomplete__option-value">{suggestion.value}</span>
                {suggestion.context && (
                  <span className="autocomplete__option-context">{suggestion.context}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {error && (
        <span className="field-error" id={errorId} role="alert">
          {error}
        </span>
      )}
    </label>
  );
}
