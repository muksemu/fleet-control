import { $, safe, statusTag, sourceLabel, isFreshSimulation } from "./utils.js";
import { sendJSON } from "./api.js";

// Создаётся один раз. getData() всегда возвращает последний ответ сервера.

export function createFleet({ getData, loadData, showView }) {
  let selectedTruckId = null;
  let draftStatus = null;

  function renderFleet() {
    const data = getData();
    const search = $("search").value.toLocaleLowerCase("ru-RU").trim();
    const filter = $("fleet-filter").value;
    const trucks = data.trucks.filter(
      (t) =>
        (!filter || t.status === filter) &&
        [t.name, t.id, t.driver].some((field) =>
          String(field).toLocaleLowerCase("ru-RU").includes(search),
        ),
    );
    $("fleet-count").textContent = `${trucks.length} из ${data.trucks.length}`;
    $("fleet-table").innerHTML = trucks.length
      ? trucks
          .map(
            (t) => `
      <tr class="${t.id === selectedTruckId ? "selected-row" : ""}">
        <td class="row-id">#${t.id}</td><td><strong>${safe(t.name)}</strong></td>
        <td>${safe(t.driver)}</td><td>${statusTag(t.status)}</td>
        <td><button class="row-action" data-truck-id="${t.id}">Открыть ↗</button></td></tr>`,
          )
          .join("")
      : '<tr><td colspan="5" class="empty">Машины не найдены</td></tr>';
    if ($("truck-dialog").open) renderTruckDetail();
  }

  function telemetryLabel(position, truck, trip) {
    if (!position) return "Нет данных";
    if (position.source !== "simulated") return sourceLabel(position.source);
    if (!isFreshSimulation(position)) return "Нет свежих тестовых координат";
    const moving =
      trip && truck.status === "В пути" && Number(position.speed_kmh) > 0;
    return moving ? "GPS-симулятор: едет (тест)" : "GPS-симулятор: стоит (тест)";
  }

  function renderTruckDetail() {
    const data = getData();
    if (!$("truck-dialog").open) return;
    const t = data.trucks.find((truck) => truck.id === selectedTruckId);
    if (!t) {
      $("truck-dialog").close();
      return;
    }
    const position = data.positions.find((p) => p.truck_id === t.id);
    const trip = data.trips.find(
      (r) => r.truck_id === t.id && r.status === "В пути",
    );
    const telemetryInfo = telemetryLabel(position, t, trip);
    const selected = draftStatus || t.status;
    const allowedStatuses = trip ? ["В пути"] : ["На месте", "На ремонте"];
    const choices = allowedStatuses
      .map((s) => `<option ${s === selected ? "selected" : ""}>${s}</option>`)
      .join("");
    const hint = trip
      ? `Машина выполняет рейс #${trip.id}. Чтобы изменить её статус, сначала завершите рейс.`
      : t.status === "В пути"
        ? "У машины статус «В пути», но активного рейса нет. Можно исправить статус здесь."
        : "Статус «В пути» появится автоматически, когда вы начнёте рейс.";

    // Во время автоматического обновления сохраняем фокус, если человек выбирает статус.
    const editWasFocused = document.activeElement?.id === "edit-status";
    $("fleet-detail").innerHTML = `
      <div class="truck-hero">
        <div class="detail-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="31" height="31" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 6h11v10H3zM14 9h3.4l3.6 3.5V16h-7z"/>
            <circle cx="7" cy="17.5" r="1.8"/><circle cx="18" cy="17.5" r="1.8"/>
          </svg>
        </div>
        <div class="truck-hero-text">
          <p class="detail-label">ТРАНСПОРТ · #${t.id}</p>
          <h3>${safe(t.name)}</h3>
          ${statusTag(t.status)}
        </div>
      </div>
      <div class="truck-detail-grid">
        <section class="truck-detail-section" aria-label="Информация о машине">
          <h4>Информация</h4>
          <dl class="info-list">
            <div><dt>Водитель</dt><dd>${safe(t.driver)}</dd></div>
            <div><dt>Активный рейс</dt><dd>${trip ? `#${trip.id}: ${safe(trip.origin)} → ${safe(trip.destination)}` : "Нет"}</dd></div>
          </dl>
        </section>
        <section class="truck-detail-section" aria-label="Данные о местоположении">
          <h4>Местоположение</h4>
          <dl class="info-list">
            <div><dt>Координаты</dt><dd>${position ? `${Number(position.latitude).toFixed(3)}, ${Number(position.longitude).toFixed(3)}` : "Нет данных"}</dd></div>
            <div><dt>Время записи</dt><dd>${position ? new Date(position.recorded_at).toLocaleString("ru-RU") : "—"}</dd></div>
            <div><dt>Источник</dt><dd>${safe(telemetryInfo)}</dd></div>
            <div><dt>Скорость</dt><dd>${position?.speed_kmh != null ? `${Number(position.speed_kmh).toFixed(1)} км/ч` : "—"}</dd></div>
          </dl>
        </section>
      </div>
      <section class="truck-status-section" aria-label="Управление статусом">
        <h4>Статус машины</h4>
        <label class="field-label" for="edit-status">Изменить статус</label>
        <select id="edit-status" ${trip ? "disabled" : ""}>${choices}</select>
        <p class="field-hint">${hint}</p>
        ${trip ? "" : '<button type="button" class="primary-button" id="save-truck">Сохранить статус</button>'}
      </section>`;
    if (editWasFocused) $("edit-status").focus({ preventScroll: true });
  }

  function openTruck(id, fromMap = false) {
    const data = getData();
    if (!data.trucks.some((t) => t.id === id)) return;
    if (fromMap) {
      // Машина с карты должна быть видна, даже если ранее был выбран фильтр.
      $("search").value = "";
      $("fleet-filter").value = "";
      showView("fleet");
    }
    selectedTruckId = id;
    draftStatus = null;
    $("truck-error").hidden = true;
    $("truck-dialog").showModal();
    renderFleet();
  }

  async function changeStatus() {
    const status = $("edit-status").value;
    const id = selectedTruckId;
    if (!id) return;
    const errorBox = $("truck-error");
    errorBox.hidden = true;
    try {
      await sendJSON(`/api/trucks/${id}/status`, "PATCH", { status });
      draftStatus = null;
      await loadData();
    } catch (error) {
      // Ошибка должна быть видна внутри открытой карточки, а не за затемнённым фоном.
      errorBox.textContent = error.message;
      errorBox.hidden = false;
    }
  }

  $("search").addEventListener("input", renderFleet);
  $("fleet-filter").addEventListener("change", renderFleet);
  $("fleet-table").addEventListener("click", (event) => {
    const button = event.target.closest("[data-truck-id]");
    if (button) openTruck(Number(button.dataset.truckId));
  });
  $("fleet-detail").addEventListener("change", (event) => {
    if (event.target.id === "edit-status") draftStatus = event.target.value;
  });
  $("fleet-detail").addEventListener("click", (event) => {
    if (event.target.id === "save-truck") changeStatus();
  });
  $("close-truck-dialog").addEventListener("click", () =>
    $("truck-dialog").close(),
  );
  $("close-truck-footer").addEventListener("click", () =>
    $("truck-dialog").close(),
  );
  $("truck-dialog").addEventListener("close", () => {
    selectedTruckId = null;
    draftStatus = null;
    renderFleet();
  });
  $("truck-dialog").addEventListener("click", (event) => {
    // Закрываем только по клику на затемнение, не по содержимому карточки.
    const rect = event.currentTarget.getBoundingClientRect();
    if (
      event.clientX < rect.left ||
      event.clientX > rect.right ||
      event.clientY < rect.top ||
      event.clientY > rect.bottom
    ) {
      event.currentTarget.close();
    }
  });

  // Добавление грузовика доступно только администратору.
  if ($("new-truck")) {
    const dialog = $("new-truck-dialog");
    $("new-truck").addEventListener("click", () => {
      $("new-truck-error").hidden = true;
      dialog.showModal();
    });
    $("close-new-truck").addEventListener("click", () => dialog.close());
    $("cancel-new-truck").addEventListener("click", () => dialog.close());
    $("new-truck-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const submit = event.target.querySelector('[type="submit"]');
      submit.disabled = true;
      try {
        await sendJSON("/api/trucks", "POST", {
          name: $("new-truck-name").value.trim(),
          driver: $("new-truck-driver").value.trim(),
        });
        dialog.close();
        event.target.reset();
        await loadData();
      } catch (error) {
        $("new-truck-error").textContent = error.message;
        $("new-truck-error").hidden = false;
      } finally {
        submit.disabled = false;
      }
    });
  }

  function closeMissingTruck() {
    if (selectedTruckId !== null &&
        !getData().trucks.some((truck) => truck.id === selectedTruckId)) {
      $("truck-dialog").close();
    }
  }

  return { render: renderFleet, openTruck, closeMissingTruck };
}
