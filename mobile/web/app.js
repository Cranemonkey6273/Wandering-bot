const DASHBOARD_URL = "https://dayzwanderingbot.com/app?source=native_android";
const LANGUAGE_STORAGE_KEY = "wanderingUiLanguage";
const SUPPORTED_LANGUAGES = new Set(["en", "de", "fr", "es", "pl"]);
const TRANSLATIONS = globalThis.WANDERING_MOBILE_TRANSLATIONS || {en: {}};
const DATA_URLS = {
  crafting: "./data/dayz_crafting_library.json",
  illnesses: "./data/dayz_illness_library.json",
  files: "./data/dayz_file_guide_library.json",
  tiers: "./data/dayz_tier_guide.json"
};

const state = {
  section: "home",
  libraries: {},
  search: "",
  platform: "all",
  map: "all",
  category: "all"
};

function safeLanguage(value) {
  const code = String(value || "").trim().toLowerCase().split(/[-_]/)[0];
  return SUPPORTED_LANGUAGES.has(code) ? code : "en";
}

function requestedLanguage() {
  const query = new URLSearchParams(window.location.search).get("lang");
  if (query) return safeLanguage(query);
  try {
    const saved = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (saved) return safeLanguage(saved);
  } catch (_) {}
  return safeLanguage(navigator.language || "en");
}

state.language = requestedLanguage();

function t(english, replacements = {}) {
  const phrase = state.language === "en" ? english : (TRANSLATIONS[state.language]?.[english] || english);
  return String(phrase).replace(/\{(\w+)\}/g, (match, key) => Object.hasOwn(replacements, key) ? String(replacements[key]) : match);
}

function translateStaticInterface() {
  document.documentElement.lang = state.language;
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    const english = element.dataset.i18n;
    element.textContent = t(english);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    element.placeholder = t(element.dataset.i18nPlaceholder);
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
    element.setAttribute("aria-label", t(element.dataset.i18nAriaLabel));
  });
  const selector = byId("language-select");
  if (selector) selector.value = state.language;
}

async function setLanguage(value) {
  state.language = safeLanguage(value);
  try { localStorage.setItem(LANGUAGE_STORAGE_KEY, state.language); } catch (_) {}
  translateStaticInterface();
  updateConnection();
  if (state.section !== "home") await renderLibrary();
}

const byId = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const searchable = (value) => JSON.stringify(value ?? "").toLowerCase();
const list = (items, ordered = false) => {
  if (!Array.isArray(items) || !items.length) return "";
  const tag = ordered ? "ol" : "ul";
  return `<${tag}>${items.map((item) => `<li>${escapeHtml(typeof item === "string" ? item : item.name || "")}</li>`).join("")}</${tag}>`;
};

function updateConnection() {
  const online = navigator.onLine !== false;
  byId("connection-label").textContent = online ? t("Online") : t("Offline");
  byId("connection-dot").classList.toggle("offline", !online);
  byId("offline-banner").hidden = online;
  const dashboard = byId("open-dashboard");
  dashboard.disabled = !online;
  dashboard.setAttribute("aria-disabled", String(!online));
  dashboard.querySelector("small").textContent = online ? t("Secure online access") : t("Reconnect to continue");
}

function openDashboard() {
  if (navigator.onLine === false) {
    updateConnection();
    return;
  }
  window.location.assign(DASHBOARD_URL);
}

async function getLibrary(name) {
  if (state.libraries[name]) return state.libraries[name];
  const response = await fetch(DATA_URLS[name], {cache: "no-store"});
  if (!response.ok) throw new Error(t("Bundled {name} library could not be opened.", {name}));
  const payload = await response.json();
  state.libraries[name] = payload;
  return payload;
}

function setCategories(items) {
  const select = byId("category-filter");
  const categories = [...new Set(items.map((item) => item.category).filter(Boolean))].sort();
  select.innerHTML = `<option value="all">${escapeHtml(t("All categories"))}</option>` + categories
    .map((category) => `<option value="${escapeHtml(category)}">${escapeHtml(t(category))}</option>`).join("");
  select.value = categories.includes(state.category) ? state.category : "all";
  state.category = select.value;
}

function resetFilters() {
  state.search = "";
  state.platform = "all";
  state.map = "all";
  state.category = "all";
  byId("library-search").value = "";
  byId("platform-filter").value = "all";
  byId("map-filter").value = "all";
  byId("category-filter").value = "all";
}

function filterItems(items) {
  const query = state.search.trim().toLowerCase();
  return items.filter((item) => {
    if (query && !searchable(item).includes(query)) return false;
    if (state.category !== "all" && item.category !== state.category) return false;
    if (state.platform !== "all" && Array.isArray(item.platforms) && !item.platforms.includes(state.platform)) return false;
    if (state.map !== "all" && Array.isArray(item.maps) && !item.maps.includes(state.map)) return false;
    return true;
  });
}

function craftCard(item) {
  const ingredients = item.ingredients?.map((part) => `${part.quantity ? `${part.quantity} × ` : ""}${part.name}`) || [];
  const alternatives = (item.alternatives || []).map((option) => {
    const parts = option.ingredients?.map((part) => `${part.quantity ? `${part.quantity} × ` : ""}${part.name}`).join(" + ") || "";
    return `<li><strong>${escapeHtml(option.label)}</strong>: ${escapeHtml(parts)}</li>`;
  }).join("");
  return `<article class="guide-card">
    <div class="card-title"><span class="card-icon">🧰</span><div><span>${escapeHtml(t(item.category))}</span><h3>${escapeHtml(item.name)}</h3></div></div>
    <div class="guide-block"><strong>${escapeHtml(t("What you need"))}</strong>${list(ingredients)}</div>
    ${item.tools?.length ? `<div class="guide-block"><strong>${escapeHtml(t("Tools"))}</strong>${list(item.tools)}</div>` : ""}
    <div class="guide-block"><strong>${escapeHtml(t("How to make it"))}</strong>${list(item.steps, true)}</div>
    ${alternatives ? `<div class="guide-block"><strong>${escapeHtml(t("Alternatives"))}</strong><ul>${alternatives}</ul></div>` : ""}
    ${item.notes ? `<p class="note">${escapeHtml(item.notes)}</p>` : ""}
  </article>`;
}

function illnessCard(item) {
  const priority = String(item.priority || "standard").toLowerCase();
  return `<article class="guide-card priority-${escapeHtml(priority)}">
    <div class="card-title"><span class="card-icon">🩺</span><div><span>${escapeHtml(t(item.category))} · ${escapeHtml(t(priority))}</span><h3>${escapeHtml(item.name)}</h3></div></div>
    <div class="guide-block"><strong>${escapeHtml(t("Symptoms"))}</strong>${list(item.symptoms)}</div>
    <div class="guide-block"><strong>${escapeHtml(t("Likely causes"))}</strong>${list(item.causes)}</div>
    <div class="guide-block treatment"><strong>${escapeHtml(t("What to do"))}</strong>${list(item.treatment, true)}</div>
    <div class="guide-block"><strong>${escapeHtml(t("Prevention"))}</strong>${list(item.prevention)}</div>
    ${item.notes ? `<p class="note warning-note">${escapeHtml(item.notes)}</p>` : ""}
  </article>`;
}

function fileCard(item) {
  return `<article class="guide-card">
    <div class="card-title"><span class="card-icon">🗂️</span><div><span>${escapeHtml(t(item.category))} · ${escapeHtml(item.format)}</span><h3>${escapeHtml(item.name)}</h3></div></div>
    <code class="file-path">${escapeHtml(item.location)}</code>
    <p>${escapeHtml(item.purpose)}</p>
    <div class="guide-block"><strong>${escapeHtml(t("Works with"))}</strong>${list(item.works_with)}</div>
    <p><strong>${escapeHtml(t("How it links:"))}</strong> ${escapeHtml(item.relationship)}</p>
    <p><strong>${escapeHtml(t("Restart:"))}</strong> ${escapeHtml(item.restart)}</p>
    <p class="note warning-note"><strong>${escapeHtml(t("Important:"))}</strong> ${escapeHtml(item.warning)}</p>
  </article>`;
}

function termCard(item) {
  return `<article class="term-card">
    <span>${escapeHtml(t(item.category))}</span><h3>${escapeHtml(item.term)}</h3>
    <p>${escapeHtml(item.meaning)}</p><p class="note"><strong>${escapeHtml(t("Rule:"))}</strong> ${escapeHtml(item.rule)}</p>
  </article>`;
}

function tierCard(mapKey, item) {
  return `<article class="tier-card">
    <span class="tier-dot" style="--tier-colour:${escapeHtml(item.colour)}">${escapeHtml(item.number)}</span>
    <div><h3>${escapeHtml(t("Tier {number} — {area}", {number: item.number, area: item.area}))}</h3><p>${escapeHtml(item.description)}</p></div>
  </article>`;
}

function renderEmpty() {
  byId("library-content").innerHTML = `<div class="empty-card"><strong>${escapeHtml(t("No matching entries"))}</strong><span>${escapeHtml(t("Try clearing a filter or using a broader search."))}</span></div>`;
}

async function renderLibrary() {
  const section = state.section;
  const content = byId("library-content");
  content.innerHTML = `<div class="loading-card">${escapeHtml(t("Loading the bundled guide…"))}</div>`;
  try {
    const data = await getLibrary(section);
    byId("release-badge").textContent = `DayZ ${data.active_release || "bundled"}`;
    byId("library-note").textContent = data.coverage_note || t("Stored inside the app for offline use.");
    byId("platform-filter-wrap").hidden = section !== "crafting";
    byId("map-filter-wrap").hidden = section === "files" || section === "tiers";
    byId("category-filter-wrap").hidden = section === "tiers";
    byId("library-search").placeholder = section === "tiers" ? t("Search map notes") : t("Search {section}", {section: t(section === "illnesses" ? "Health" : section === "files" ? "Files" : "Crafting")});

    if (section === "crafting") {
      byId("library-title").textContent = t("Crafting & building");
      const items = data.recipes || [];
      setCategories(items);
      const filtered = filterItems(items);
      byId("library-summary").textContent = t("{shown} of {total} reviewed recipes", {shown: filtered.length, total: items.length});
      content.innerHTML = filtered.map(craftCard).join("");
      if (!filtered.length) renderEmpty();
      return;
    }

    if (section === "illnesses") {
      byId("library-title").textContent = t("Illnesses & treatment");
      const items = data.illnesses || [];
      setCategories(items);
      const filtered = filterItems(items);
      byId("library-summary").textContent = t("{shown} of {total} reviewed conditions", {shown: filtered.length, total: items.length});
      content.innerHTML = filtered.map(illnessCard).join("");
      if (!filtered.length) renderEmpty();
      return;
    }

    if (section === "files") {
      byId("library-title").textContent = t("DayZ files explained");
      const combined = [
        ...(data.files || []).map((item) => ({...item, _kind: "file"})),
        ...(data.terms || []).map((item) => ({...item, _kind: "term"}))
      ];
      setCategories(combined);
      const filtered = filterItems(combined);
      byId("library-summary").textContent = t("{shown} of {total} file and term explanations", {shown: filtered.length, total: combined.length});
      content.innerHTML = filtered.map((item) => item._kind === "file" ? fileCard(item) : termCard(item)).join("");
      if (!filtered.length) renderEmpty();
      return;
    }

    byId("library-title").textContent = t("Loot tiers & maps");
    const maps = data.maps || {};
    const mapKeys = Object.keys(maps);
    const selectedKey = state.map !== "all" && maps[state.map] ? state.map : mapKeys[0];
    state.map = selectedKey;
    const selected = maps[selectedKey];
    const query = state.search.trim().toLowerCase();
    const mapOptions = mapKeys.map((key) => `<button type="button" class="map-chip ${key === selectedKey ? "active" : ""}" data-map="${escapeHtml(key)}">${escapeHtml(maps[key].label)}</button>`).join("");
    const matches = !query || searchable(selected).includes(query);
    byId("library-summary").innerHTML = `<div class="map-switcher">${mapOptions}</div>`;
    content.innerHTML = matches ? `<article class="tier-map-card">
      <img src="./data/tier_maps/${escapeHtml(selectedKey)}.webp" alt="${escapeHtml(selected.image_alt)}">
      <div class="tier-map-copy"><span>${escapeHtml(selected.mission)}</span><h3>${escapeHtml(selected.label)}</h3><p>${escapeHtml(selected.summary)}</p></div>
    </article>${(selected.tiers || []).map((item) => tierCard(selectedKey, item)).join("")}
    <article class="note-card"><strong>${escapeHtml(t("PC community maps"))}</strong><p>${escapeHtml(t("Use the exact mission files supplied by the map author. The app does not guess tier overlays for modded terrains."))}</p></article>` : "";
    if (!matches) renderEmpty();
    document.querySelectorAll("[data-map]").forEach((button) => button.addEventListener("click", () => {
      state.map = button.dataset.map;
      renderLibrary();
    }));
  } catch (error) {
    content.innerHTML = `<div class="error-card"><strong>${escapeHtml(t("Offline guide unavailable"))}</strong><span>${escapeHtml(error.message)}</span></div>`;
  }
}

async function showSection(section) {
  state.section = section;
  document.querySelectorAll(".page").forEach((page) => page.classList.toggle("active", section === "home" ? page.dataset.page === "home" : page.dataset.page === "library"));
  document.querySelectorAll(".bottom-nav button").forEach((button) => button.classList.toggle("active", button.dataset.section === section));
  if (section !== "home") {
    resetFilters();
    await renderLibrary();
  }
  window.scrollTo({top: 0, behavior: "smooth"});
}

window.addEventListener("load", () => {
  translateStaticInterface();
  document.querySelectorAll("[data-section]").forEach((button) => button.addEventListener("click", () => showSection(button.dataset.section)));
  byId("language-select").addEventListener("change", (event) => setLanguage(event.target.value));
  byId("open-dashboard").addEventListener("click", openDashboard);
  byId("library-search").addEventListener("input", (event) => { state.search = event.target.value; renderLibrary(); });
  byId("platform-filter").addEventListener("change", (event) => { state.platform = event.target.value; renderLibrary(); });
  byId("map-filter").addEventListener("change", (event) => { state.map = event.target.value; renderLibrary(); });
  byId("category-filter").addEventListener("change", (event) => { state.category = event.target.value; renderLibrary(); });
  window.addEventListener("online", updateConnection);
  window.addEventListener("offline", updateConnection);
  updateConnection();
});
