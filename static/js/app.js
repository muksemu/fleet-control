import { $, safe, dateTime } from "./utils.js";
import { api } from "./api.js";
import { createFleet } from "./fleet.js";
import { createTrips } from "./trips.js";
import { createMap } from "./map.js";
import { initAccount } from "./account.js";

// Единственное место хранения общей сводки. Модули читают её через getData().
let data = { trucks: [], trips: [], positions: [], events: [] };
let refreshing = false;
const getData = () => data;

const fleet = createFleet({ getData, loadData, showView });
const trips = createTrips({ getData, loadData, showError });
const mapView = createMap({ getData, openTruck: fleet.openTruck });
const account = initAccount();

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = !message;
}

async function loadData() {
  if (refreshing) return;
  refreshing = true;
  try {
    data = await api("/api/dashboard", { cache: "no-store" });
    fleet.closeMissingTruck();
    showError("");
    $("connection-text").textContent = "Данные получены";
    $("connection-dot").className = "connected";
    $("last-update").textContent =
      `Обновлено в ${new Date().toLocaleTimeString("ru-RU")}`;
    render();
  } catch (error) {
    showError(error.message);
    $("connection-text").textContent = "Нет подключения";
    $("connection-dot").className = "disconnected";
  } finally {
    refreshing = false;
  }
}

function renderMetrics() {
  const total = data.trucks.length;
  const driving = data.trucks.filter((t) => t.status === "В пути").length;
  const home = data.trucks.filter((t) => t.status === "На месте").length;
  const repair = data.trucks.filter((t) => t.status === "На ремонте").length;
  $("stat-total").textContent = total;
  $("stat-driving").textContent = driving;
  $("stat-home").textContent = home;
  $("stat-repair").textContent = repair;

  $("distribution").innerHTML = [
    ["В пути", driving, "#277e73"],
    ["На месте", home, "#4079b4"],
    ["На ремонте", repair, "#c28b4a"],
  ]
    .map(
      ([name, count, color]) =>
        `<div class="dist-item"><div class="dist-label"><span>${name}</span><strong>${count} из ${total}</strong></div><div class="dist-track"><div style="width:${total ? (100 * count) / total : 0}%;background:${color}"></div></div></div>`,
    )
    .join("");
}

function eventMarkup(event) {
  return `<div class="event"><span class="event-symbol">↳</span><div><strong>${safe(event.description)}</strong>
    <p>${safe(event.truck_name || "Система")} · ${dateTime(event.created_at)}</p></div></div>`;
}

function renderEvents() {
  const empty =
    '<p class="empty">Событий пока нет. Они появятся после изменения статуса или создания рейса.</p>';
  $("events-table").innerHTML = data.events.length
    ? data.events.map(eventMarkup).join("")
    : empty;
  $("overview-events").innerHTML = data.events.length
    ? data.events.slice(0, 4).map(eventMarkup).join("")
    : empty;
}

function renderAlerts() {
  const alerts = data.alerts || [];
  $("alerts-count").textContent = alerts.length;
  $("overview-alerts").innerHTML = alerts.length
    ? alerts
        .map(
          (
            alert,
          ) => `<div class="alert-entry"><span class="alert-symbol">!</span>
        <span>${safe(alert.message)}</span>
        <button type="button" class="row-action" data-alert-truck="${Number(alert.truck_id)}">Открыть машину</button></div>`,
        )
        .join("")
    : '<p class="alerts-ok">Сейчас нет предупреждений по активным рейсам.</p>';
}

function render() {
  renderMetrics();
  trips.render();
  fleet.render();
  renderEvents();
  renderAlerts();
  // Карта создаётся только при первом открытии, а затем обновляются маркеры.
  mapView.render();
  trips.updateNewTripButton();
}

function showView(view) {
  const titles = {
    overview: [
      "Оперативная сводка",
      "Обзор",
      "Транспорт, рейсы и события в единой рабочей области",
    ],
    fleet: [
      "Автопарк",
      "Автопарк",
      "Реестр транспорта и управление состоянием машин",
    ],
    trips: [
      "Управление рейсами",
      "Рейсы",
      "Назначение перевозок и контроль выполнения",
    ],
    events: ["История событий", "События", "Изменения и действия диспетчера"],
    account: ["Личный кабинет", "Профиль", "Личные данные и настройки входа"],
  };
  document.querySelectorAll(".view").forEach((section) => {
    section.hidden = section.id !== `view-${view}`;
  });
  document
    .querySelectorAll("[data-view]")
    .forEach((button) =>
      button.classList.toggle("active", button.dataset.view === view),
    );
  $("page-title").textContent = titles[view][0];
  $("page-eyebrow").textContent =
    view === "account" ? "УЧЁТНАЯ ЗАПИСЬ" : "ЦЕНТР УПРАВЛЕНИЯ ПЕРЕВОЗКАМИ";
  $("header-controls").hidden = view === "account";
  $("page-description").textContent = titles[view][2];
  if (view === "overview") mapView.resize();
  if (view === "account" && $("staff-list")) account.loadUsers();
}

// События интерфейса: одно место, где видно, какая кнопка что запускает.
document
  .querySelectorAll("[data-view]")
  .forEach((button) =>
    button.addEventListener("click", () => showView(button.dataset.view)),
  );
document
  .querySelectorAll("[data-go]")
  .forEach((button) =>
    button.addEventListener("click", () => showView(button.dataset.go)),
  );
$("refresh").addEventListener("click", loadData);

$("overview-alerts").addEventListener("click", (event) => {
  const button = event.target.closest("[data-alert-truck]");
  if (button) fleet.openTruck(Number(button.dataset.alertTruck));
});

loadData();
setInterval(() => {
  if (document.visibilityState === "visible") loadData();
}, 10000);
