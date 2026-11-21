"use strict";

const find = (id) => document.getElementById(id);
const country = find("country");
const postcode = find("postcode");
const manual = find("manual");
const statusLine = find("lookup-status");
const retry = find("retry");
const levelsBox = find("levels");
const preview = find("preview-text");
const copyButton = find("copy");
const detailFields = ["manual-place", "street-extra", "building", "unit"];
const formatNames = typeof Intl.DisplayNames === "function"
  ? new Intl.DisplayNames(["ja"], {type: "region"}) : null;
const regionName = (code) => formatNames?.of(code) ?? code;
const kinds = {
  area: "地域", region: "都道府県・州", state: "都道府県・州", city: "市区町村",
  town: "町域・地区", locality: "地域名", street: "通り", house_number: "番地",
  facility: "施設", building: "建物", address: "住所", qualifier: "該当する範囲", routing_name: "郵便用の都市名",
};
const examples = {JP: "064-0941", US: "20001", FR: "75007", GB: "SW1A 1AA", CA: "K1A 0A9"};
const laPosteCountries = new Set(["BL", "FR", "GF", "GP", "MC", "MF", "MQ", "NC", "PF", "PM", "RE", "WF", "YT"]);
const noPostcode = new Set(["HK", "MO"]);
const cache = new Map();
const drafts = new Map();
let available = null;
let countriesReady = false;
let countriesFailed = false;
let epoch = 0;
let timer;
let controller;
let levels = [];
let sources = [];
let scope = "";
let manualPreference = null;
let composing = false;
let lastRetry = null;

function setStatus(message, error = false, retryAction = null) {
  statusLine.textContent = message;
  statusLine.toggleAttribute("data-error", error);
  lastRetry = retryAction;
  retry.hidden = !retryAction;
}

function postalKey() {
  const value = postcode.value.normalize("NFKC").trim();
  if (country.value === "JP") {
    return value.replace(/^(\d{3})[-‐‑－](\d{4})$/, "$1$2");
  }
  return value.toUpperCase();
}

function updateManual(enabled) {
  manual.checked = enabled;
  find("manual-fields").hidden = !enabled;
  levelsBox.hidden = enabled;
}

function remember(map, key, value, max) {
  map.delete(key);
  map.set(key, value);
  if (map.size > max) map.delete(map.keys().next().value);
}

function syncScope() {
  const key = country.value + "\n" + postalKey();
  if (scope === key) return false;
  if (scope) {
    remember(drafts, scope, {
      values: detailFields.map(id => find(id).value), manualPreference,
    }, 40);
  }
  scope = key;
  const draft = drafts.get(key);
  detailFields.forEach((id, i) => { find(id).value = draft?.values[i] ?? ""; });
  manualPreference = draft?.manualPreference ?? null;
  updateManual(manualPreference ?? noPostcode.has(country.value));
  levels = [];
  sources = [];
  levelsBox.replaceChildren();
  return true;
}

function cancelPending() {
  clearTimeout(timer);
  controller?.abort();
  controller = new AbortController();
  return ++epoch;
}

function chosen() {
  return levels.flatMap(level => level.choice ? [level.choice] : []);
}

function addressData() {
  const selected = manual.checked ? [] : chosen();
  return {
    country: country.value, postcode: postcode.value.trim(),
    selected: selected.map(({id, label, kind}) => ({id, label, kind})),
    manual_place: manual.checked ? find("manual-place").value.trim() : "",
    street_extra: find("street-extra").value.trim(), building: find("building").value.trim(),
    unit: find("unit").value.trim(), sources: selected.length ? [...sources] : [],
    deliverability_verified: false,
  };
}

function addressLines(data) {
  const physical = data.selected.filter(row => row.kind !== "qualifier");
  const parts = physical.map(row => row.label);
  const suffix = [data.building, data.unit].filter(Boolean).join(" ");
  if (data.country === "JP") {
    const code = postalKey().replace(/^(\d{3})(\d{4})$/, "$1-$2");
    return [code && "〒" + code, [...parts, data.manual_place, data.street_extra].join(""), suffix].filter(Boolean);
  }
  if (data.country === "US") {
    const streetKinds = new Set(["house_number", "street", "address"]);
    const street = ["address", "house_number", "street"].flatMap(
      kind => physical.filter(row => row.kind === kind).map(row => row.label)
    ).join(" ");
    const place = [...physical.filter(row => !streetKinds.has(row.kind)).map(row => row.label), data.manual_place];
    return [[street, data.street_extra].filter(Boolean).join(" "), suffix,
      [...place, data.postcode].filter(Boolean).join(" "), regionName(data.country)].filter(Boolean);
  }
  if (laPosteCountries.has(data.country)) {
    const city = physical.find(row => row.kind === "routing_name") ?? physical.find(row => row.kind === "area");
    const localities = physical.filter(row => row.kind !== "routing_name" && row.kind !== "area");
    return [suffix, data.street_extra, ...localities.map(row => row.label),
      [data.postcode, city?.label, data.manual_place].filter(Boolean).join(" "), regionName(data.country)].filter(Boolean);
  }
  return [regionName(data.country), data.postcode, ...parts, data.manual_place, data.street_extra, suffix].filter(Boolean);
}

function refreshPreview() {
  const data = addressData();
  const hasAddress = data.selected.some(row => row.kind !== "qualifier") ||
    Boolean(data.manual_place || data.street_extra || data.building || data.unit);
  const hasContent = hasAddress || Boolean(data.postcode);
  preview.classList.toggle("empty", !hasContent);
  preview.textContent = hasContent ? addressLines(data).join("\n") : "入力すると、ここに住所が表示されます。";
  copyButton.disabled = !hasAddress;
  find("copy-status").textContent = "";
  document.dispatchEvent(new CustomEvent("veygrit:address-change", {bubbles: true, detail: data}));
}

function focusedElementId() {
  const active = document.activeElement;
  return levelsBox.contains(active) ? active.id : "";
}

function renderLevels() {
  const focused = focusedElementId();
  const fragment = document.createDocumentFragment();
  levels.forEach((level, depth) => {
    const box = document.createElement("div");
    box.className = "field level";
    const label = document.createElement("label");
    const select = document.createElement("select");
    select.id = "level-" + depth;
    label.htmlFor = select.id;
    const keys = [...new Set(level.options.map(item => item.kind))];
    const title = keys.length === 1 ? kinds[keys[0]] ?? "住所" : "住所";
    label.textContent = title + "の候補";
    select.add(new Option("選択してください", ""));
    for (const row of level.options) {
      const name = keys.length > 1 && kinds[row.kind] ? kinds[row.kind] + "　" + row.label : row.label;
      select.add(new Option(name, row.id));
    }
    select.value = level.choice?.id ?? "";
    select.addEventListener("change", () => choose(depth, select.value));
    box.append(label, select);
    if (!level.choice && level.options.length) {
      const hints = document.createElement("p");
      hints.className = "level-preview";
      hints.id = select.id + "-preview";
      const labels = level.options.slice(0, 3).map(item => item.label);
      const more = level.options.length > labels.length || level.after !== null;
      hints.textContent = labels.join("、") + (more ? " ほか" : "");
      select.setAttribute("aria-describedby", hints.id);
      box.append(hints);
    }
    if (level.after !== null && !level.choice) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "text-action";
      button.id = "more-" + depth;
      button.textContent = "候補をさらに読み込む";
      button.addEventListener("click", () => loadNextPage(depth));
      box.append(button);
    }
    fragment.append(box);
  });
  levelsBox.replaceChildren(fragment);
  if (focused) (find(focused) ?? find(focused.replace("more-", "level-")))?.focus({preventScroll: true});
}

async function fetchOptions(path, after, signal) {
  const params = new URLSearchParams({country: country.value, postcode: postalKey()});
  for (const id of path) params.append("path", id);
  if (after !== null) params.set("after", String(after));
  const key = params.toString();
  if (cache.has(key)) return cache.get(key);
  const response = await fetch("/api/postal?" + key, {signal, cache: "no-store"});
  if (!response.ok) throw new Error("lookup failed");
  const result = await response.json();
  if (!Array.isArray(result.options) || !Array.isArray(result.selected) ||
      !["options", "leaf", "unsupported_country", "not_found"].includes(result.status)) {
    throw new Error("unexpected response");
  }
  remember(cache, key, result, 100);
  return result;
}

async function loadLevel(path, sequence, {after = null} = {}) {
  const depth = path.length;
  setStatus("候補を検索中…");
  try {
    const result = await fetchOptions(path, after, controller.signal);
    if (sequence !== epoch) return;
    sources = result.sources ?? [];
    if (after !== null) {
      const level = levels[depth];
      const ids = new Set(level.options.map(row => row.id));
      level.options.push(...result.options.filter(row => !ids.has(row.id)));
      level.after = result.next_after ?? null;
      renderLevels();
      setStatus("選択できる候補を追加しました。");
      return;
    }
    if (result.status === "options" && result.options.length) {
      const level = {options: result.options, after: result.next_after ?? null, choice: null};
      levels[depth] = level;
      const only = level.options.length === 1 && level.after === null ? level.options[0] : null;
      // A unique broad area can be shown immediately. More specific details are chosen by the user.
      if (depth === 0 && only?.kind === "area" && only.has_children) {
        level.choice = only;
        renderLevels();
        refreshPreview();
        return loadLevel([only.id], sequence);
      }
      renderLevels();
      setStatus(depth ? "続く住所を候補から選んでください。" : "郵便番号に対応する候補が見つかりました。");
    } else if (result.status === "leaf") {
      setStatus("この原典の候補はここまでです。残りの番地・建物名などを入力してください。");
    } else {
      setStatus(result.status === "unsupported_country"
        ? "この国・地域は手入力で住所を指定できます。"
        : "この郵便番号の候補は収録されていません。住所を手入力できます。");
      if (!path.length && manualPreference === null) updateManual(true);
    }
    refreshPreview();
  } catch (error) {
    if (sequence !== epoch || error.name === "AbortError") return;
    setStatus("候補を取得できませんでした。再検索するか、住所を手入力してください。",
      true, () => loadLevel(path, cancelPending(), {after}));
  }
}

function loadNextPage(depth) {
  const level = levels[depth];
  if (!level || level.after === null) return;
  const path = levels.slice(0, depth).map(row => row.choice.id);
  loadLevel(path, cancelPending(), {after: level.after});
}

function choose(depth, id) {
  const level = levels[depth];
  const choice = level.options.find(row => row.id === id) ?? null;
  const sequence = cancelPending();
  level.choice = choice;
  levels.length = depth + 1;
  sources = [];
  renderLevels();
  refreshPreview();
  if (choice) loadLevel(chosen().map(row => row.id), sequence);
  else setStatus("住所の候補を選んでください。");
}

function search(immediate = false) {
  const sequence = cancelPending();
  syncScope();
  refreshPreview();
  if (!countriesReady) {
    if (countriesFailed) showCountryError();
    else setStatus("国・地域の一覧を読み込んでいます。");
    return;
  }
  if (!available.has(country.value)) {
    if (manualPreference === null) updateManual(true);
    setStatus(noPostcode.has(country.value) ? "郵便番号を省略して住所を手入力できます。"
      : "この国・地域は手入力で住所を指定できます。");
    return;
  }
  if (manual.checked && manualPreference === true) {
    setStatus("手入力で住所を指定できます。");
    return;
  }
  const code = postalKey();
  if (!code) {
    setStatus("郵便番号を入力してください。");
    return;
  }
  const digits = expectedDigits();
  if (digits && !(new RegExp("^\\d{" + digits + "}$")).test(code)) {
    setStatus("郵便番号を" + digits + "桁で入力してください。");
    return;
  }
  setStatus("候補を検索中…");
  // Retain an existing path when retrying the same code or changing only its notation.
  const path = chosen().map(row => row.id);
  timer = setTimeout(() => loadLevel(path, sequence), immediate ? 0 : 140);
}

function setCountry() {
  postcode.placeholder = examples[country.value] ? "例　" + examples[country.value] : "";
  postcode.inputMode = expectedDigits() ? "numeric" : "text";
  postcode.disabled = noPostcode.has(country.value) && !available?.has(country.value);
  search(true);
}

function expectedDigits() {
  if (country.value === "JP") return 7;
  if (country.value === "US" || laPosteCountries.has(country.value)) return 5;
  return null;
}

async function loadCountries() {
  countriesFailed = false;
  setStatus("国・地域の一覧を読み込んでいます。");
  try {
    const response = await fetch("/api/countries", {cache: "no-store"});
    if (!response.ok) throw new Error("countries failed");
    const result = await response.json();
    if (!Array.isArray(result.countries) || !result.countries.length) throw new Error("countries missing");
    available = new Set(result.available ?? result.countries);
    const selected = country.value;
    const options = result.countries.map(code => new Option(regionName(code) + " (" + code + ")", code));
    options.sort((a, b) => a.label.localeCompare(b.label, "ja"));
    country.replaceChildren(...options);
    if (result.countries.includes(selected)) country.value = selected;
    countriesReady = true;
    setCountry();
  } catch {
    countriesFailed = true;
    showCountryError();
    updateManual(true);
  }
}

function showCountryError() {
  setStatus("国・地域を読み込めませんでした。再試行するか、表示中の国の住所を手入力してください。", true, loadCountries);
}

country.addEventListener("change", () => {
  postcode.value = "";
  setCountry();
});
postcode.addEventListener("compositionstart", () => { composing = true; cancelPending(); });
postcode.addEventListener("compositionend", () => { composing = false; search(); });
postcode.addEventListener("input", () => { if (!composing) search(); });
postcode.addEventListener("keydown", event => {
  if (event.key === "Enter" && !composing) { event.preventDefault(); search(true); }
});
find("address-form").addEventListener("submit", event => { event.preventDefault(); });
retry.addEventListener("click", () => lastRetry?.());
manual.addEventListener("change", () => {
  manualPreference = manual.checked;
  updateManual(manual.checked);
  if (manual.checked) {
    cancelPending();
    setStatus("地域名や通りを手入力してください。");
    find("manual-place").focus();
  } else search(true);
  refreshPreview();
});
detailFields.forEach(id => find(id).addEventListener("input", refreshPreview));
copyButton.addEventListener("click", async () => {
  const text = preview.textContent;
  try {
    await navigator.clipboard.writeText(text);
    find("copy-status").textContent = "住所をコピーしました。";
  } catch {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(preview);
    selection.removeAllRanges();
    selection.addRange(range);
    find("copy-status").textContent = "住所を選択しました。端末のコピー操作を使ってください。";
  }
});

syncScope();
refreshPreview();
loadCountries();
