import { useState } from "react";

const initialState = {
  currentLocation: "",
  pickupLocation: "",
  dropoffLocation: "",
  currentCycleUsedHours: "",
};

export default function TripForm({ onSubmit, loading }) {
  const [form, setForm] = useState(initialState);

  function handleChange(e) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  function handleSubmit(e) {
    e.preventDefault();
    onSubmit(form);
  }

  return (
    <form className="trip-form" onSubmit={handleSubmit}>
      <label>
        Current location
        <input name="currentLocation" value={form.currentLocation} onChange={handleChange} required />
      </label>
      <label>
        Pickup location
        <input name="pickupLocation" value={form.pickupLocation} onChange={handleChange} required />
      </label>
      <label>
        Dropoff location
        <input name="dropoffLocation" value={form.dropoffLocation} onChange={handleChange} required />
      </label>
      <label>
        Current cycle used (hrs)
        <input
          name="currentCycleUsedHours"
          type="number"
          min="0"
          max="70"
          step="0.5"
          value={form.currentCycleUsedHours}
          onChange={handleChange}
          required
        />
      </label>
      <button type="submit" disabled={loading}>
        {loading ? "Planning..." : "Plan trip"}
      </button>
    </form>
  );
}
