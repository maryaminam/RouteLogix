const API_URL = import.meta.env?.VITE_API_URL || "http://127.0.0.1:8000";

/**
 * What went wrong, so the UI can explain it in the user's terms rather than
 * echoing a raw message. Each maps to a distinct backend failure path:
 *
 *   VALIDATION - TripRequestSerializer rejected a field (DRF field errors, 400)
 *   GEOCODING  - a location string couldn't be resolved to coordinates (400)
 *   ROUTING    - locations resolved but OSRM couldn't connect them (502)
 *   SERVER     - anything else the API returned
 *   NETWORK    - the request never reached the API at all
 */
export const ERROR_KIND = {
  VALIDATION: "validation",
  GEOCODING: "geocoding",
  ROUTING: "routing",
  SERVER: "server",
  NETWORK: "network",
};

export class ApiError extends Error {
  constructor(message, { status = null, kind = ERROR_KIND.SERVER, fieldErrors = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.kind = kind;
    this.fieldErrors = fieldErrors;
  }
}

// DRF reports field errors as {field: ["msg", ...]}, occasionally with a bare
// string instead of a list. Flatten to {field: "msg. msg."} for display.
function flattenFieldErrors(body) {
  const entries = Object.entries(body)
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([field, value]) => [field, Array.isArray(value) ? value.join(" ") : String(value)])
    .filter(([, message]) => message.length > 0);

  return entries.length ? Object.fromEntries(entries) : null;
}

function toApiError(body, status) {
  // The view returns {"detail": ...} for geocoding (400) and routing (502)
  // failures; DRF's own validation errors arrive as a field map instead.
  if (typeof body?.detail === "string") {
    return new ApiError(body.detail, {
      status,
      kind: status === 400 ? ERROR_KIND.GEOCODING : ERROR_KIND.ROUTING,
    });
  }

  if (status === 400) {
    const fieldErrors = flattenFieldErrors(body || {});
    if (fieldErrors) {
      return new ApiError(Object.values(fieldErrors).join(" "), {
        status,
        kind: ERROR_KIND.VALIDATION,
        fieldErrors,
      });
    }
  }

  if (status === 502) {
    return new ApiError("The routing service is unavailable.", { status, kind: ERROR_KIND.ROUTING });
  }

  return new ApiError(`The server returned an unexpected error (HTTP ${status}).`, {
    status,
    kind: ERROR_KIND.SERVER,
  });
}

/**
 * The IANA zone this browser is running in, e.g. "America/Chicago".
 *
 * FMCSA logs record every time in the driver's home terminal zone, so the
 * planner needs one to decide where each 24-hour log sheet begins. We take the
 * browser's zone as a stand-in: a driver planning a trip is overwhelmingly
 * likely to be doing it on home terminal time.
 *
 * Falls back to UTC only if the runtime won't report a zone, which keeps a
 * request from failing validation over a detail the user never entered.
 */
export function detectTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export async function planTrip({ currentLocation, pickupLocation, dropoffLocation, currentCycleUsedHours }) {
  let response;
  try {
    response = await fetch(`${API_URL}/api/trips/plan/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current_location: currentLocation,
        pickup_location: pickupLocation,
        dropoff_location: dropoffLocation,
        current_cycle_used_hours: Number(currentCycleUsedHours),
        home_terminal_timezone: detectTimezone(),
      }),
    });
  } catch {
    // fetch only rejects when the request never completed — DNS, refused
    // connection, CORS, offline. HTTP error statuses resolve normally.
    throw new ApiError(`Couldn't reach the planning service at ${API_URL}.`, {
      kind: ERROR_KIND.NETWORK,
    });
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw toApiError(body, response.status);
  }

  return response.json();
}

/**
 * Typeahead suggestions for a location field.
 *
 * Pass an AbortSignal so superseded keystrokes can be cancelled; an aborted
 * request rejects with a DOMException named "AbortError", which callers should
 * treat as "nothing to do" rather than as a failure.
 *
 * Throws ApiError when suggestions genuinely can't be fetched. Callers should
 * degrade rather than block — the field still accepts free text.
 */
export async function searchLocations(query, { signal } = {}) {
  let response;
  try {
    response = await fetch(
      `${API_URL}/api/locations/search/?q=${encodeURIComponent(query)}`,
      { signal }
    );
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new ApiError("Couldn't reach the suggestion service.", { kind: ERROR_KIND.NETWORK });
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(body?.detail || "Suggestions are unavailable.", {
      status: response.status,
      kind: ERROR_KIND.SERVER,
    });
  }

  const body = await response.json();
  return body.results || [];
}

export { API_URL };
