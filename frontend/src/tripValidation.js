// Mirrors TripRequestSerializer (backend/trips/serializers.py) so the user is
// told before the round trip, not after. The backend stays the authority — see
// api.js for how its 400 response is surfaced when the two ever disagree.
export const MIN_CYCLE_HOURS = 0;
export const MAX_CYCLE_HOURS = 70;

// Mirrors LOCATION_SEARCH_MIN_QUERY_LENGTH in settings.py — below this the
// endpoint returns an empty list without calling out, so don't bother asking.
export const LOCATION_SEARCH_MIN_LENGTH = 3;

export const LOCATION_FIELDS = [
  { name: "currentLocation", label: "Current location", hint: "Where the driver is right now" },
  { name: "pickupLocation", label: "Pickup location", hint: "Where the load is collected" },
  { name: "dropoffLocation", label: "Dropoff location", hint: "Where the load is delivered" },
];

/** Returns {field: message} for every invalid field; empty object when valid. */
export function validateTripForm(form) {
  const errors = {};

  for (const { name, label } of LOCATION_FIELDS) {
    if (!String(form[name] ?? "").trim()) {
      errors[name] = `${label} is required.`;
    }
  }

  const raw = String(form.currentCycleUsedHours ?? "").trim();
  if (!raw) {
    errors.currentCycleUsedHours = "Enter the hours already used in the 70-hour cycle.";
  } else {
    const hours = Number(raw);
    if (!Number.isFinite(hours)) {
      errors.currentCycleUsedHours = "Enter a number of hours.";
    } else if (hours < MIN_CYCLE_HOURS || hours > MAX_CYCLE_HOURS) {
      errors.currentCycleUsedHours = `Must be between ${MIN_CYCLE_HOURS} and ${MAX_CYCLE_HOURS} hours.`;
    }
  }

  return errors;
}
