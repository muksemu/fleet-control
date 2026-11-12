// Общие функции отображения. Запросов и состояния приложения здесь нет.
export const $ = (id) => document.getElementById(id);
export const dateTime = (value) =>
  value
    ? new Date(value).toLocaleString("ru-RU", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
export const safe = (value) =>
  String(value ?? "—").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );

// Источник точки нельзя путать с состоянием грузовика или статусом рейса.
export const sourceLabel = (source) =>
  ({
    simulated: "GPS-симулятор (тест)",
    manual: "Введено вручную",
    unknown: "Источник не указан",
  })[source] || "Источник не указан";
export const isFreshSimulation = (position) =>
  position.source === "simulated" &&
  Date.now() - new Date(position.recorded_at).getTime() < 45000;

export function statusTag(status) {
  const types = {
    "В пути": "driving",
    "На месте": "home",
    "На ремонте": "repair",
  };
  const type = types[status] || "pending";
  return `<span class="status-tag ${type}"><i></i>${safe(status)}</span>`;
}
