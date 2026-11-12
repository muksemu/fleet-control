// Все HTTP-запросы проходят через одну обработку CSRF, сессии и ошибок.
export async function api(url, options = {}) {
  const headers = { ...options.headers };
  if (options.method && options.method.toUpperCase() !== "GET") {
    headers["X-CSRF-Token"] = document.querySelector(
      'meta[name="csrf-token"]',
    ).content;
  }
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    window.location.assign("/login");
    throw new Error("Сессия завершена. Войди снова.");
  }
  const isJSON = response.headers
    .get("Content-Type")
    ?.includes("application/json");
  const result = isJSON ? await response.json() : null;
  if (!response.ok)
    throw new Error(result?.error || `Ошибка HTTP ${response.status}`);
  if (!isJSON) throw new Error("Сервер вернул ответ в неожиданном формате");
  return result;
}

export function sendJSON(url, method, payload) {
  return api(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
