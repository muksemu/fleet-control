import { $, safe, dateTime, statusTag } from "./utils.js";
import { sendJSON } from "./api.js";

// Формы и действия рейсов. После сохранения запрашиваем общие данные заново.

export function createTrips({ getData, loadData, showError }) {
  // Для рейса показываем только действие, которое сейчас разрешено.
  function tripAction(trip) {
    const data = getData();
    if (trip.status === "Завершён") return "—";
    if (trip.status === "Запланирован") {
      const truck = data.trucks.find((t) => t.id === trip.truck_id);
      if (truck?.status === "На ремонте")
        return '<span class="blocked-action">Машина на ремонте</span>';
      if (
        data.trips.some(
          (t) =>
            t.truck_id === trip.truck_id &&
            t.id !== trip.id &&
            t.status === "В пути",
        )
      ) {
        return '<span class="blocked-action">Машина в другом рейсе</span>';
      }
    }
    const next = trip.status === "Запланирован" ? "В пути" : "Завершён";
    const label =
      trip.status === "Запланирован" ? "Начать рейс" : "Завершить рейс";
    return `<button type="button" class="row-action trip-action" data-trip-id="${trip.id}" data-status="${next}">${label}</button>`;
  }

  function renderTrips() {
    const data = getData();
    const active = data.trips.filter((t) => t.status !== "Завершён").slice(0, 5);
    $("overview-trips").innerHTML = active.length
      ? active
          .map(
            (trip) => `
      <div class="trip-entry"><div class="trip-meta"><span>РЕЙС #${trip.id}</span>${statusTag(trip.status)}</div>
        <strong>${safe(trip.origin)} <span class="arrow">→</span> ${safe(trip.destination)}</strong>
        <div class="trip-sub">${safe(trip.truck_name)} <span>·</span> Прибытие: ${dateTime(trip.eta_at)}</div>
      </div>`,
          )
          .join("")
      : '<p class="empty">Нет активных рейсов. Создайте новый в разделе «Рейсы».</p>';

    $("trips-table").innerHTML = data.trips.length
      ? data.trips
          .map(
            (trip) => `
      <tr><td class="row-id">#${trip.id}</td><td><strong>${safe(trip.truck_name)}</strong></td>
        <td>${safe(trip.origin)} <span class="arrow">→</span> ${safe(trip.destination)}</td>
        <td>${dateTime(trip.eta_at)}</td><td>${statusTag(trip.status)}</td>
        <td>${tripAction(trip)}</td></tr>`,
          )
          .join("")
      : '<tr><td colspan="6" class="empty">Рейсов пока нет. Создайте первый.</td></tr>';
  }

  async function createTrip(event) {
    event.preventDefault();
    const errorBox = $("trip-error");
    errorBox.hidden = true;
    const etaValue = $("trip-eta").value;
    const etaDate = new Date(etaValue);
    if (!etaValue || Number.isNaN(etaDate.getTime()) || etaDate <= new Date()) {
      errorBox.textContent = "Укажите дату и время прибытия в будущем.";
      errorBox.hidden = false;
      return;
    }
    const origin = $("trip-origin").value.trim();
    const destination = $("trip-destination").value.trim();
    if (
      origin.toLocaleLowerCase("ru-RU") === destination.toLocaleLowerCase("ru-RU")
    ) {
      errorBox.textContent = "Пункт отправления и назначения должны различаться.";
      errorBox.hidden = false;
      return;
    }
    const payload = {
      truck_id: Number($("trip-truck").value),
      origin,
      destination,
      eta_at: etaDate.toISOString(),
    };
    try {
      await sendJSON("/api/trips", "POST", payload);
      $("trip-dialog").close();
      $("trip-form").reset();
      await loadData();
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.hidden = false;
    }
  }

  async function changeTripStatus(button) {
    try {
      await sendJSON(`/api/trips/${button.dataset.tripId}/status`, "PATCH", {
        status: button.dataset.status,
      });
      await loadData();
    } catch (error) {
      // После перерисовки возвращаем выбор, но не теряем сообщение об ошибке.
      await loadData();
      showError(error.message);
    }
  }

  function updateNewTripButton() {
    const data = getData();
    const available = data.trucks.some((t) => t.status !== "На ремонте");
    $("new-trip").disabled = !available;
    $("new-trip").title = available
      ? ""
      : "Нет доступных машин для назначения рейса";
  }

  $("trips-table").addEventListener("click", (event) => {
    const button = event.target.closest("[data-trip-id]");
    if (button) changeTripStatus(button);
  });

  $("new-trip").addEventListener("click", () => {
    const data = getData();
    const available = data.trucks.filter((t) => t.status !== "На ремонте");
    if (!available.length) return;
    $("trip-truck").innerHTML = available
      .map(
        (t) =>
          `<option value="${t.id}">${safe(t.name)} — ${safe(t.driver)}</option>`,
      )
      .join("");
    $("trip-error").hidden = true;
    $("trip-dialog").showModal();
  });

  $("close-dialog").addEventListener("click", () => $("trip-dialog").close());
  $("cancel-trip").addEventListener("click", () => $("trip-dialog").close());
  $("trip-form").addEventListener("submit", createTrip);
  updateNewTripButton();

  return { render: renderTrips, updateNewTripButton };
}
