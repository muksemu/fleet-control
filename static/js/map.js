import { $, safe, dateTime, sourceLabel, isFreshSimulation } from "./utils.js";

// Карта не импортирует автопарк: функцию openTruck передаёт app.js.

export function createMap({ getData, openTruck }) {
  let map = null;
  let markers = null;
  let routeLines = null;
  let mapInitiallyFitted = false;
  let lastMapRoutes = "";
  let tileMessage = null;
  let tileCheckTimer = null;
  const tileStates = new Map();
  const TILE_WAIT_MS = 15000;
  const TILE_SETTLE_MS = 1500;

  function scheduleTileCheck(delay = TILE_SETTLE_MS) {
    clearTimeout(tileCheckTimer);
    tileCheckTimer = setTimeout(checkTiles, delay);
  }

  function checkTiles() {
    tileCheckTimer = null;
    const bounds = $("map").getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;

    // Учитываем видимую область и текущий масштаб, исключая старые фрагменты.
    const visible = [...tileStates].filter(([tile, state]) => {
      if (state.zoom !== map.getZoom()) return false;
      const rect = tile.getBoundingClientRect();
      return tile.isConnected && rect.right > bounds.left &&
        rect.left < bounds.right && rect.bottom > bounds.top &&
        rect.top < bounds.bottom;
    }).map(([, state]) => state);

    if (!visible.length || visible.some((state) => state.status === "loaded")) {
      tileMessage.hidden = true;
      return;
    }

    const pending = visible.filter((state) => state.status === "pending");
    const remaining = pending.map((state) =>
      TILE_WAIT_MS - (Date.now() - state.startedAt));
    const wait = Math.max(0, ...remaining);
    if (wait > 0) {
      scheduleTileCheck(wait);
      return;
    }

    // Один ошибочный фрагмент не означает отказ всей карты.
    tileMessage.hidden = visible.length < 2;
  }

  function watchTiles(layer) {
    layer.on("tileloadstart", ({ tile, coords }) => {
      tileStates.set(tile, { status: "pending", zoom: coords.z, startedAt: Date.now() });
      scheduleTileCheck();
    });
    layer.on("tileload", ({ tile, coords }) => {
      tileStates.set(tile, { status: "loaded", zoom: coords.z });
      tileMessage.hidden = true;
      scheduleTileCheck();
    });
    layer.on("tileerror", ({ tile, coords }) => {
      tileStates.set(tile, { status: "failed", zoom: coords.z });
      scheduleTileCheck();
    });
    layer.on("tileunload", ({ tile }) => {
      tileStates.delete(tile);
      scheduleTileCheck();
    });
    map.on("moveend zoomend resize", () => scheduleTileCheck());
    map.on("unload", () => {
      clearTimeout(tileCheckTimer);
      tileStates.clear();
    });
  }

  function renderMap() {
    const data = getData();
    const validPositions = data.positions.filter((p) =>
      data.trucks.some((t) => t.id === p.truck_id),
    );
    $("map-count").textContent = validPositions.length;
    const simulated = validPositions.filter((p) => p.source === "simulated");
    const fresh = simulated.filter(isFreshSimulation).length;
    $("gps-state").textContent = simulated.length
      ? fresh
        ? `Тестовый сигнал: ${fresh} из ${simulated.length} машин`
        : "Тестовый сигнал не поступает"
      : "GPS-источник не подключён";
    if (!window.L) {
      const message = $("map-loading");
      message.textContent = "Не удалось загрузить карту. Проверьте подключение к интернету и обновите страницу";
      message.setAttribute("role", "status");
      return;
    }
    renderLeafletMap(validPositions);
  }

  function renderLeafletMap(validPositions) {
    const data = getData();
    if (!map) {
      $("map-loading")?.remove();
      map = L.map("map", { zoomControl: false }).setView([56.7, 39.6], 5);
      L.control.zoom({ position: "bottomright" }).addTo(map);
      tileMessage = document.createElement("div");
      tileMessage.className = "map-message";
      tileMessage.setAttribute("role", "status");
      tileMessage.textContent = "Не удалось загрузить изображение карты. Проверьте подключение к интернету и обновите страницу";
      tileMessage.hidden = true;
      $("map").append(tileMessage);
      const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18,
        referrerPolicy: "strict-origin-when-cross-origin",
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
      });
      watchTiles(tiles);
      tiles.addTo(map);
      markers = L.layerGroup().addTo(map);
      routeLines = L.layerGroup().addTo(map);
    }
    markers.clearLayers();
    routeLines.clearLayers();
    // Линии соединяют города по прямой.
    for (const route of data.routes || []) {
      L.polyline(route.coordinates, {
        color: route.status === "В пути" ? "#95dfad" : "#738f80",
        weight: route.status === "В пути" ? 3 : 2,
        opacity: 0.65,
        dashArray: "6 8",
      }).addTo(routeLines);
    }
    for (const p of validPositions) {
      const t = data.trucks.find((item) => item.id === p.truck_id);
      const stale = p.source === "simulated" && !isFreshSimulation(p);
      L.circleMarker([p.latitude, p.longitude], {
        radius: 8,
        color: stale ? "#c0c6c2" : "#c5e8d1",
        weight: 2,
        fillColor: stale ? "#7f8d85" : "#6bd99b",
        fillOpacity: 1,
      })
        .bindPopup(
          `<strong>${safe(t?.name || `Машина #${p.truck_id}`)}</strong><p>${safe(sourceLabel(p.source))}${stale ? " · Нет свежего сигнала" : ""}</p><small>Записано: ${safe(dateTime(p.recorded_at))}</small>`,
        )
        .on("click", () => openTruck(p.truck_id, true))
        .addTo(markers);
    }
    // Обновление координат не сбрасывает выбранный масштаб.
    const routeKey = (data.routes || [])
      .map((r) => `${r.trip_id}:${r.coordinates.join(";")}`)
      .join("|");
    if (!mapInitiallyFitted || routeKey !== lastMapRoutes) {
      const points = validPositions.map((p) => [p.latitude, p.longitude]);
      for (const route of data.routes || []) points.push(...route.coordinates);
      if (points.length) {
        map.fitBounds(points, { padding: [40, 40], maxZoom: 7 });
        mapInitiallyFitted = true;
      }
      lastMapRoutes = routeKey;
    }
  }

  function resize() {
    if (map) setTimeout(() => {
      map.invalidateSize();
      scheduleTileCheck();
    }, 0);
  }

  return { render: renderMap, resize };
}
