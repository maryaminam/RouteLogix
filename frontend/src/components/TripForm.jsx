import { useState } from "react";
import LocationAutocomplete from "./LocationAutocomplete";
import {
  LOCATION_FIELDS,
  MAX_CYCLE_HOURS,
  MIN_CYCLE_HOURS,
  validateTripForm,
} from "../tripValidation";

const initialState = {
  currentLocation: "",
  pickupLocation: "",
  dropoffLocation: "",
  currentCycleUsedHours: "",
};

export default function TripForm({ onSubmit, loading }) {
  const [form, setForm] = useState(initialState);
  const [touched, setTouched] = useState({});

  const errors = validateTripForm(form);
  const isValid = Object.keys(errors).length === 0;

  function setField(name, value) {
    setForm((previous) => ({ ...previous, [name]: value }));
  }

  function handleChange(event) {
    setField(event.target.name, event.target.value);
  }

  // Errors stay hidden until a field has been visited, so the form doesn't
  // open covered in complaints about fields nobody has filled in yet.
  function handleBlur(event) {
    const { name } = event.target;
    setTouched((previous) => ({ ...previous, [name]: true }));
  }

  function handleSubmit(event) {
    event.preventDefault();
    if (!isValid || loading) return;

    onSubmit({
      currentLocation: form.currentLocation.trim(),
      pickupLocation: form.pickupLocation.trim(),
      dropoffLocation: form.dropoffLocation.trim(),
      currentCycleUsedHours: form.currentCycleUsedHours,
    });
  }

  function errorFor(name) {
    return touched[name] ? errors[name] : undefined;
  }

  const cycleError = errorFor("currentCycleUsedHours");

  return (
    <form className="trip-form" onSubmit={handleSubmit} noValidate>
      {LOCATION_FIELDS.map(({ name, label, hint }) => (
        <LocationAutocomplete
          key={name}
          name={name}
          label={label}
          hint={hint}
          value={form[name]}
          error={errorFor(name)}
          onValueChange={setField}
          onBlur={handleBlur}
        />
      ))}

      <label>
        Current cycle used (hrs)
        <input
          type="number"
          name="currentCycleUsedHours"
          min={MIN_CYCLE_HOURS}
          max={MAX_CYCLE_HOURS}
          step="0.5"
          placeholder={`${MIN_CYCLE_HOURS}–${MAX_CYCLE_HOURS}`}
          value={form.currentCycleUsedHours}
          onChange={handleChange}
          onBlur={handleBlur}
          aria-invalid={cycleError ? "true" : undefined}
          aria-describedby={cycleError ? "currentCycleUsedHours-error" : undefined}
        />
        {cycleError && (
          <span className="field-error" id="currentCycleUsedHours-error" role="alert">
            {cycleError}
          </span>
        )}
      </label>

      <div className="trip-form__actions">
        <button type="submit" disabled={!isValid || loading}>
          {loading ? "Planning..." : "Plan trip"}
        </button>
        {!isValid && !loading && (
          <p className="trip-form__hint">Fill in all four fields to plan the trip.</p>
        )}
      </div>
    </form>
  );
}
