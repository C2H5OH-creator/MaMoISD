const state = {
  categories: [],
  products: [],
  enumerations: [],
  enumerationDetails: [],
  enumValues: {},
  cart: loadCart(),
  auth: loadAuth(),
  draftFilters: {
    query: "",
    categoryId: "",
    minPrice: "",
    maxPrice: "",
    inStockOnly: false,
    specName: "",
    specValue: "",
    sortBy: "default",
  },
  appliedFilters: {
    query: "",
    categoryId: "",
    minPrice: "",
    maxPrice: "",
    inStockOnly: false,
    specName: "",
    specValue: "",
    sortBy: "default",
  },
  editingCategoryId: null,
  editingProductId: null,
};

const els = {
  statsTitle: document.querySelector("#statsTitle"),
  categoriesCount: document.querySelector("#categoriesCount"),
  productsCount: document.querySelector("#productsCount"),
  specsCount: document.querySelector("#specsCount"),
  categoryGrid: document.querySelector("#categoryGrid"),
  productGrid: document.querySelector("#productGrid"),
  emptyProducts: document.querySelector("#emptyProducts"),
  cartCounts: document.querySelectorAll(".cart-count"),
  cartItems: document.querySelector("#cartItems"),
  emptyCart: document.querySelector("#emptyCart"),
  cartTotal: document.querySelector("#cartTotal"),
  clearCartButton: document.querySelector("#clearCartButton"),
  checkoutButton: document.querySelector("#checkoutButton"),
  searchInput: document.querySelector("#searchInput"),
  categorySelect: document.querySelector("#categorySelect"),
  minPriceInput: document.querySelector("#minPriceInput"),
  maxPriceInput: document.querySelector("#maxPriceInput"),
  inStockInput: document.querySelector("#inStockInput"),
  specFilterSelect: document.querySelector("#specFilterSelect"),
  specValueInput: document.querySelector("#specValueInput"),
  sortSelect: document.querySelector("#sortSelect"),
  applyFiltersButton: document.querySelector("#applyFiltersButton"),
  resetFiltersButton: document.querySelector("#resetFiltersButton"),
  filterSummary: document.querySelector("#filterSummary"),
  toast: document.querySelector("#toast"),
  parentCategorySelect: document.querySelector("#parentCategorySelect"),
  productCategorySelect: document.querySelector("#productCategorySelect"),
  categoryForm: document.querySelector("#categoryForm"),
  productForm: document.querySelector("#productForm"),
  enumerationForm: document.querySelector("#enumerationForm"),
  enumValueForm: document.querySelector("#enumValueForm"),
  parameterForm: document.querySelector("#parameterForm"),
  adminForms: document.querySelector("#adminForms"),
  loginForm: document.querySelector("#loginForm"),
  logoutButton: document.querySelector("#logoutButton"),
  authStatus: document.querySelector("#authStatus"),
  adminMessage: document.querySelector("#adminMessage"),
  categoryFormTitle: document.querySelector("#categoryFormTitle"),
  productFormTitle: document.querySelector("#productFormTitle"),
  categorySubmitButton: document.querySelector("#categorySubmitButton"),
  productSubmitButton: document.querySelector("#productSubmitButton"),
  categoryCancelButton: document.querySelector("#categoryCancelButton"),
  productCancelButton: document.querySelector("#productCancelButton"),
  specRows: document.querySelector("#specRows"),
  addSpecButton: document.querySelector("#addSpecButton"),
  enumValueEnumSelect: document.querySelector("#enumValueEnumSelect"),
  enumItemTypeSelect: document.querySelector("#enumItemTypeSelect"),
  enumValueTextWrap: document.querySelector("#enumValueTextWrap"),
  enumChildWrap: document.querySelector("#enumChildWrap"),
  enumChildSelect: document.querySelector("#enumChildSelect"),
  enumValuesList: document.querySelector("#enumValuesList"),
  parameterCategorySelect: document.querySelector("#parameterCategorySelect"),
  parameterTypeSelect: document.querySelector("#parameterTypeSelect"),
  parameterEnumWrap: document.querySelector("#parameterEnumWrap"),
  parameterEnumSelect: document.querySelector("#parameterEnumSelect"),
  categoryParametersList: document.querySelector("#categoryParametersList"),
};

function loadCart() {
  try {
    const rawCart = localStorage.getItem("mispris-cart");
    if (!rawCart) {
      return {};
    }
    const parsed = JSON.parse(rawCart);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {};
    }
    return Object.fromEntries(
      Object.entries(parsed)
        .map(([productId, quantity]) => [productId, Number(quantity)])
        .filter(([, quantity]) => Number.isInteger(quantity) && quantity > 0),
    );
  } catch {
    return {};
  }
}

function saveCart() {
  localStorage.setItem("mispris-cart", JSON.stringify(state.cart));
}

function loadAuth() {
  try {
    const rawAuth = localStorage.getItem("mispris-auth");
    if (!rawAuth) {
      return null;
    }
    const auth = JSON.parse(rawAuth);
    if (!auth?.accessToken || !auth?.role || !auth?.expiresAt) {
      return null;
    }
    if (Number(auth.expiresAt) <= Date.now()) {
      localStorage.removeItem("mispris-auth");
      return null;
    }
    return auth;
  } catch {
    return null;
  }
}

function saveAuth(auth) {
  if (!auth) {
    localStorage.removeItem("mispris-auth");
    return;
  }
  localStorage.setItem("mispris-auth", JSON.stringify(auth));
}

function isAdmin() {
  return state.auth?.role === "admin";
}

function getAuthHeaders() {
  if (!state.auth?.accessToken) {
    return {};
  }
  return {
    Authorization: `Bearer ${state.auth.accessToken}`,
  };
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = `HTTP ${response.status}: ${url}`;
    try {
      const payload = await response.json();
      detail = payload.detail ?? detail;
    } catch {
      // Response body is optional for error states.
    }
    throw new Error(detail);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function formatPrice(value) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0,
  }).format(value);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function getCategoryName(categoryId) {
  return state.categories.find((category) => category.id === categoryId)?.name ?? "Без категории";
}

function getSpecValue(spec) {
  if (spec.value !== null && spec.value !== undefined) {
    const customUnit = spec.custom_unit_short_name ? ` ${spec.custom_unit_short_name}` : "";
    return `${spec.value}${customUnit}`;
  }

  if (spec.enum_value_id !== null && spec.enum_value_id !== undefined) {
    return state.enumValues[String(spec.enum_value_id)] ?? `enum #${spec.enum_value_id}`;
  }

  return "не задано";
}

function getAvailableSpecs() {
  const names = new Set();
  for (const product of state.products) {
    for (const spec of product.specifications ?? []) {
      names.add(spec.name);
    }
  }
  return [...names].sort((left, right) => left.localeCompare(right, "ru"));
}

function getFinalEnumValues() {
  return state.enumerationDetails.flatMap((enumeration) =>
    (enumeration.values ?? [])
      .filter((item) => item.item_type === "value" && item.value !== null)
      .map((item) => ({
        id: item.id,
        value: item.value,
        enumId: enumeration.id,
        enumName: enumeration.name,
      })),
  );
}

function fillEnumerationSelect(select, placeholder, excludeEnumId = null) {
  select.innerHTML = "";
  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = placeholder;
  select.append(defaultOption);

  for (const enumeration of state.enumerations) {
    if (excludeEnumId !== null && enumeration.id === excludeEnumId) {
      continue;
    }
    const option = document.createElement("option");
    option.value = String(enumeration.id);
    option.textContent = enumeration.name;
    select.append(option);
  }
}

function fillEnumValueSelect(select, selectedValue = "") {
  select.innerHTML = '<option value="">Выберите значение</option>';
  for (const item of getFinalEnumValues()) {
    const option = document.createElement("option");
    option.value = String(item.id);
    option.textContent = `${item.enumName}: ${item.value}`;
    select.append(option);
  }
  select.value = selectedValue ? String(selectedValue) : "";
}

function getPriceBounds() {
  if (state.products.length === 0) {
    return { min: 0, max: 0 };
  }

  const prices = state.products.map((product) => Number(product.price));
  return {
    min: Math.min(...prices),
    max: Math.max(...prices),
  };
}

function productMatchesText(product) {
  const query = state.appliedFilters.query.trim().toLowerCase();
  if (!query) {
    return true;
  }

  const specText = (product.specifications ?? [])
    .map((spec) => `${spec.name} ${getSpecValue(spec)}`)
    .join(" ")
    .toLowerCase();

  const text = [
    product.name,
    product.description ?? "",
    getCategoryName(product.category_id),
    specText,
  ]
    .join(" ")
    .toLowerCase();

  return text.includes(query);
}

function productMatchesSpec(product) {
  if (!state.appliedFilters.specName && !state.appliedFilters.specValue.trim()) {
    return true;
  }

  const expectedValue = state.appliedFilters.specValue.trim().toLowerCase();
  return (product.specifications ?? []).some((spec) => {
    const matchesName = !state.appliedFilters.specName || spec.name === state.appliedFilters.specName;
    const matchesValue = !expectedValue || getSpecValue(spec).toLowerCase().includes(expectedValue);
    return matchesName && matchesValue;
  });
}

function productMatches(product) {
  const price = Number(product.price);
  const minPrice = state.appliedFilters.minPrice === "" ? null : Number(state.appliedFilters.minPrice);
  const maxPrice = state.appliedFilters.maxPrice === "" ? null : Number(state.appliedFilters.maxPrice);

  return (
    (!state.appliedFilters.categoryId || String(product.category_id) === state.appliedFilters.categoryId)
    && productMatchesText(product)
    && (minPrice === null || price >= minPrice)
    && (maxPrice === null || price <= maxPrice)
    && (!state.appliedFilters.inStockOnly || Number(product.quantity) > 0)
    && productMatchesSpec(product)
  );
}

function sortProducts(products) {
  const sorted = [...products];
  if (state.appliedFilters.sortBy === "price-asc") {
    sorted.sort((left, right) => Number(left.price) - Number(right.price));
  } else if (state.appliedFilters.sortBy === "price-desc") {
    sorted.sort((left, right) => Number(right.price) - Number(left.price));
  } else if (state.appliedFilters.sortBy === "name-asc") {
    sorted.sort((left, right) => left.name.localeCompare(right.name, "ru"));
  } else if (state.appliedFilters.sortBy === "quantity-desc") {
    sorted.sort((left, right) => Number(right.quantity) - Number(left.quantity));
  }
  return sorted;
}

function getFilteredProducts() {
  return sortProducts(state.products.filter(productMatches));
}

function getCartQuantity(productId) {
  return state.cart[String(productId)] ?? 0;
}

function getCartEntries() {
  return Object.entries(state.cart)
    .map(([productId, quantity]) => ({
      product: state.products.find((item) => item.id === Number(productId)),
      quantity,
    }))
    .filter((entry) => entry.product);
}

function renderStats() {
  const specsCount = state.products.reduce(
    (count, product) => count + (product.specifications?.length ?? 0),
    0,
  );

  els.statsTitle.textContent = "Каталог подключен";
  els.categoriesCount.textContent = state.categories.length;
  els.productsCount.textContent = state.products.length;
  els.specsCount.textContent = specsCount;
}

function renderFilters() {
  const currentSpecName = state.draftFilters.specName;
  const priceBounds = getPriceBounds();

  els.minPriceInput.placeholder = state.products.length ? String(priceBounds.min) : "Минимальная";
  els.maxPriceInput.placeholder = state.products.length ? String(priceBounds.max) : "Максимальная";
  els.searchInput.value = state.draftFilters.query;
  els.categorySelect.value = state.draftFilters.categoryId;
  els.minPriceInput.value = state.draftFilters.minPrice;
  els.maxPriceInput.value = state.draftFilters.maxPrice;
  els.inStockInput.checked = state.draftFilters.inStockOnly;
  els.specValueInput.value = state.draftFilters.specValue;
  els.sortSelect.value = state.draftFilters.sortBy;

  els.specFilterSelect.innerHTML = '<option value="">Любая характеристика</option>';
  for (const specName of getAvailableSpecs()) {
    const option = document.createElement("option");
    option.value = specName;
    option.textContent = specName;
    els.specFilterSelect.append(option);
  }
  els.specFilterSelect.value = currentSpecName;
}

function renderFilterSummary(productsCount) {
  const activeFilters = [];
  if (state.appliedFilters.categoryId) {
    activeFilters.push(`категория: ${getCategoryName(Number(state.appliedFilters.categoryId))}`);
  }
  if (state.appliedFilters.minPrice !== "") {
    activeFilters.push(`цена от ${state.appliedFilters.minPrice}`);
  }
  if (state.appliedFilters.maxPrice !== "") {
    activeFilters.push(`цена до ${state.appliedFilters.maxPrice}`);
  }
  if (state.appliedFilters.inStockOnly) {
    activeFilters.push("только в наличии");
  }
  if (state.appliedFilters.specName) {
    activeFilters.push(`характеристика: ${state.appliedFilters.specName}`);
  }
  if (state.appliedFilters.specValue.trim()) {
    activeFilters.push(`значение: ${state.appliedFilters.specValue.trim()}`);
  }

  const prefix = `Найдено товаров: ${productsCount}.`;
  els.filterSummary.textContent = activeFilters.length
    ? `${prefix} Активные фильтры: ${activeFilters.join(", ")}.`
    : `${prefix} Фильтры не применены.`;
}

function fillCategorySelect(select, placeholder, includeRoot = false) {
  select.innerHTML = "";
  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = placeholder;
  select.append(defaultOption);

  if (includeRoot) {
    defaultOption.textContent = "Корневой раздел";
  }

  for (const category of state.categories) {
    const option = document.createElement("option");
    option.value = String(category.id);
    option.textContent = category.name;
    select.append(option);
  }
}

function addSpecRow(spec = {}) {
  const row = document.createElement("div");
  row.className = "spec-row";
  row.innerHTML = `
    <input name="spec_name" type="text" maxlength="255" placeholder="Название характеристики" value="${escapeHtml(spec.name ?? "")}" />
    <select name="spec_type">
      <option value="value">Произвольное значение</option>
      <option value="enum">Из перечисления</option>
    </select>
    <input name="spec_value" type="text" maxlength="1000" placeholder="Значение" value="${escapeHtml(spec.value ?? "")}" />
    <select name="spec_enum_value_id"></select>
    <button class="button ghost" type="button" data-action="remove-spec-row">Удалить</button>
  `;

  const typeSelect = row.querySelector('[name="spec_type"]');
  const valueInput = row.querySelector('[name="spec_value"]');
  const enumSelect = row.querySelector('[name="spec_enum_value_id"]');
  fillEnumValueSelect(enumSelect, spec.enum_value_id ?? "");
  typeSelect.value = spec.enum_value_id ? "enum" : "value";

  function syncSpecRow() {
    const enumMode = typeSelect.value === "enum";
    valueInput.hidden = enumMode;
    enumSelect.hidden = !enumMode;
  }

  typeSelect.addEventListener("change", syncSpecRow);
  syncSpecRow();
  els.specRows.append(row);
}

function resetSpecRows(specifications = []) {
  els.specRows.innerHTML = "";
  if (specifications.length === 0) {
    addSpecRow();
    return;
  }
  for (const specification of specifications) {
    addSpecRow(specification);
  }
}

function readProductSpecifications() {
  const specs = [];
  for (const row of els.specRows.querySelectorAll(".spec-row")) {
    const name = row.querySelector('[name="spec_name"]').value.trim();
    const type = row.querySelector('[name="spec_type"]').value;
    if (!name) {
      continue;
    }
    if (type === "enum") {
      const enumValueId = row.querySelector('[name="spec_enum_value_id"]').value;
      if (!enumValueId) {
        throw new Error(`Для характеристики "${name}" нужно выбрать значение перечисления`);
      }
      specs.push({
        name,
        enum_value_id: Number(enumValueId),
      });
    } else {
      const value = row.querySelector('[name="spec_value"]').value.trim();
      if (!value) {
        throw new Error(`Для характеристики "${name}" нужно заполнить значение`);
      }
      specs.push({
        name,
        value,
      });
    }
  }
  return specs;
}

function renderEnumerationControls() {
  const currentEnumValueEnumId = els.enumValueEnumSelect.value;
  const currentChildEnumId = els.enumChildSelect.value;
  const currentParameterEnumId = els.parameterEnumSelect.value;
  fillEnumerationSelect(els.enumValueEnumSelect, "Выберите перечисление");
  els.enumValueEnumSelect.value = currentEnumValueEnumId;
  fillEnumerationSelect(els.parameterEnumSelect, "Выберите перечисление");
  els.parameterEnumSelect.value = currentParameterEnumId;

  const selectedEnumId = Number(els.enumValueEnumSelect.value);
  fillEnumerationSelect(
    els.enumChildSelect,
    "Выберите перечисление",
    Number.isFinite(selectedEnumId) ? selectedEnumId : null,
  );
  els.enumChildSelect.value = currentChildEnumId;
  renderEnumValuesList();

  for (const enumSelect of els.specRows.querySelectorAll('[name="spec_enum_value_id"]')) {
    const currentValue = enumSelect.value;
    fillEnumValueSelect(enumSelect, currentValue);
  }
}

function renderEnumValuesList() {
  const enumId = Number(els.enumValueEnumSelect.value);
  const enumeration = state.enumerationDetails.find((item) => item.id === enumId);
  if (!enumeration) {
    els.enumValuesList.innerHTML = '<p>Выберите перечисление, чтобы увидеть значения.</p>';
    return;
  }
  const values = enumeration.values ?? [];
  if (values.length === 0) {
    els.enumValuesList.innerHTML = '<p>Значения пока не добавлены.</p>';
    return;
  }
  els.enumValuesList.innerHTML = values
    .map((item) => {
      const label = item.item_type === "enum" ? `enum: ${escapeHtml(item.child_name ?? "")}` : escapeHtml(item.value ?? "");
      return `<p><strong>${label}</strong><span>приоритет ${item.priority}</span></p>`;
    })
    .join("");
}

async function renderCategoryParametersList() {
  const categoryId = Number(els.parameterCategorySelect.value);
  if (!categoryId) {
    els.categoryParametersList.innerHTML = '<p>Выберите категорию, чтобы увидеть параметры.</p>';
    return;
  }
  try {
    const parameters = await fetchJson(`/database/categories/${categoryId}/parameters`);
    if (parameters.length === 0) {
      els.categoryParametersList.innerHTML = '<p>Параметры пока не назначены.</p>';
      return;
    }
    els.categoryParametersList.innerHTML = parameters
      .map((item) => {
        const parameter = item.parameter;
        const inherited = item.is_inherited ? "унаследован" : "собственный";
        const bounds = item.min_value !== null || item.max_value !== null
          ? `, диапазон ${item.min_value ?? "-∞"}...${item.max_value ?? "+∞"}`
          : "";
        return `<p><strong>${escapeHtml(parameter?.name ?? `#${item.parameter_id}`)}</strong><span>${escapeHtml(parameter?.parameter_type ?? "")}, ${inherited}${bounds}</span></p>`;
      })
      .join("");
  } catch (error) {
    els.categoryParametersList.innerHTML = `<p>Ошибка загрузки параметров: ${escapeHtml(error.message)}</p>`;
  }
}

function renderCategories() {
  const currentParentCategoryId = els.parentCategorySelect.value;
  const currentProductCategoryId = els.productCategorySelect.value;
  const currentParameterCategoryId = els.parameterCategorySelect.value;
  fillCategorySelect(els.categorySelect, "Все категории");
  fillCategorySelect(els.parentCategorySelect, "Корневой раздел", true);
  fillCategorySelect(els.productCategorySelect, "Выберите категорию");
  fillCategorySelect(els.parameterCategorySelect, "Выберите категорию");
  els.parentCategorySelect.value = currentParentCategoryId;
  els.productCategorySelect.value = currentProductCategoryId;
  els.parameterCategorySelect.value = currentParameterCategoryId;
  els.categorySelect.value = state.draftFilters.categoryId;

  if (state.categories.length === 0) {
    els.categoryGrid.innerHTML = '<p class="empty">Категории пока не созданы.</p>';
    return;
  }

  els.categoryGrid.innerHTML = "";
  for (const category of state.categories) {
    const productsCount = state.products.filter((product) => product.category_id === category.id).length;
    const adminActions = isAdmin()
      ? `
      <div class="card-actions">
        <button type="button" data-action="edit-category" data-id="${category.id}">Изменить</button>
        <button type="button" data-action="delete-category" data-id="${category.id}">Удалить</button>
      </div>
    `
      : "";
    const card = document.createElement("article");
    card.className = "category-card";
    card.innerHTML = `
      <strong>${escapeHtml(category.name)}</strong>
      <small>ID ${category.id}${category.parent_id ? `, родитель ${category.parent_id}` : ", корень"}</small>
      <div class="meta"><span>${productsCount} товаров</span></div>
      ${adminActions}
    `;
    card.addEventListener("click", (event) => {
      if (event.target.closest("[data-action]")) {
        return;
      }
      state.draftFilters.categoryId = String(category.id);
      els.categorySelect.value = state.draftFilters.categoryId;
      document.querySelector("#products").scrollIntoView({ behavior: "smooth" });
    });
    els.categoryGrid.append(card);
  }
}

function renderProducts() {
  const products = getFilteredProducts();
  els.productGrid.innerHTML = "";
  els.emptyProducts.hidden = products.length !== 0;
  renderFilterSummary(products.length);

  for (const product of products) {
    const specs = (product.specifications ?? []).slice(0, 4);
    const specItems = specs
      .map((spec) => `<li>${escapeHtml(spec.name)}: <strong>${escapeHtml(getSpecValue(spec))}</strong></li>`)
      .join("");
    const description = escapeHtml(product.description ?? "Описание товара не заполнено.");
    const categoryName = escapeHtml(getCategoryName(product.category_id));
    const productName = escapeHtml(product.name);
    const productLetter = escapeHtml(product.name.slice(0, 1).toUpperCase());
    const cartQuantity = getCartQuantity(product.id);
    const addToCartText = cartQuantity > 0 ? `В корзине: ${cartQuantity}` : "В корзину";
    const adminActions = isAdmin()
      ? `
          <button type="button" data-action="edit-product" data-id="${product.id}">Изменить</button>
          <button type="button" data-action="delete-product" data-id="${product.id}">Удалить</button>
        `
      : "";

    const card = document.createElement("article");
    card.className = "product-card";
    card.innerHTML = `
      <div class="product-media"><span>${productLetter}</span></div>
      <div class="product-body">
        <h3>${productName}</h3>
        <p>${description}</p>
        <ul class="specs-list">${specItems}</ul>
        <div class="price">${formatPrice(product.price)}</div>
        <div class="meta">
          <span>${categoryName}</span>
          <span>Остаток: ${product.quantity}</span>
        </div>
        <div class="card-actions">
          <button type="button" data-action="add-to-cart" data-id="${product.id}">${addToCartText}</button>
          ${adminActions}
        </div>
      </div>
    `;
    els.productGrid.append(card);
  }
}

function renderCart() {
  const entries = getCartEntries();
  const itemsCount = entries.reduce((total, entry) => total + entry.quantity, 0);
  const total = entries.reduce(
    (sum, entry) => sum + Number(entry.product.price) * entry.quantity,
    0,
  );

  for (const cartCount of els.cartCounts) {
    cartCount.textContent = itemsCount;
  }
  els.cartTotal.textContent = formatPrice(total);
  els.emptyCart.hidden = entries.length !== 0;
  els.clearCartButton.disabled = entries.length === 0;
  els.checkoutButton.disabled = entries.length === 0;
  els.cartItems.innerHTML = "";

  for (const { product, quantity } of entries) {
    const itemTotal = Number(product.price) * quantity;
    const cartItem = document.createElement("article");
    cartItem.className = "cart-item";
    cartItem.innerHTML = `
      <div>
        <strong>${escapeHtml(product.name)}</strong>
        <small>${escapeHtml(getCategoryName(product.category_id))} · ${formatPrice(product.price)} за шт.</small>
      </div>
      <div class="quantity-control">
        <button type="button" data-action="decrease-cart" data-id="${product.id}">−</button>
        <input type="number" min="1" max="${product.quantity}" value="${quantity}" data-action="set-cart" data-id="${product.id}" />
        <button type="button" data-action="increase-cart" data-id="${product.id}">+</button>
      </div>
      <strong>${formatPrice(itemTotal)}</strong>
      <button class="remove-cart" type="button" data-action="remove-from-cart" data-id="${product.id}">Удалить</button>
    `;
    els.cartItems.append(cartItem);
  }
}

function syncCartUi() {
  saveCart();
  renderProducts();
  renderCart();
}

function setCartQuantity(productId, quantity) {
  const product = state.products.find((item) => item.id === productId);
  if (!product) {
    return false;
  }

  const maxQuantity = Number(product.quantity);
  if (maxQuantity <= 0) {
    showToast("Товара нет в наличии.");
    return false;
  }

  const normalizedQuantity = Math.max(1, Math.min(Number(quantity), maxQuantity));
  if (!Number.isFinite(normalizedQuantity)) {
    return false;
  }

  state.cart[String(productId)] = Math.trunc(normalizedQuantity);
  syncCartUi();
  return true;
}

function addToCart(productId) {
  const product = state.products.find((item) => item.id === productId);
  if (!product) {
    return;
  }
  const nextQuantity = getCartQuantity(productId) + 1;
  const changed = setCartQuantity(productId, nextQuantity);
  if (changed) {
    const message = nextQuantity > Number(product.quantity)
      ? `В корзине уже максимальное доступное количество: ${product.name}`
      : `Добавлено в корзину: ${product.name}`;
    showToast(message);
  }
}

function removeFromCart(productId) {
  delete state.cart[String(productId)];
  syncCartUi();
}

function clearCart() {
  state.cart = {};
  syncCartUi();
}

async function deleteCategory(categoryId) {
  if (!isAdmin()) {
    showToast("Для удаления категории нужно войти как администратор.");
    return;
  }

  const category = state.categories.find((item) => item.id === categoryId);
  if (!category || !confirm(`Удалить категорию "${category.name}"?`)) {
    return;
  }

  try {
    await requestJson(`/database/categories/${categoryId}`, "DELETE");
    if (state.draftFilters.categoryId === String(categoryId)) {
      state.draftFilters.categoryId = "";
    }
    if (state.appliedFilters.categoryId === String(categoryId)) {
      state.appliedFilters.categoryId = "";
    }
    if (state.editingCategoryId === categoryId) {
      resetCategoryForm();
    }
    setAdminMessage("Категория удалена");
    await loadData();
  } catch (error) {
    setAdminMessage(`Ошибка удаления категории: ${error.message}`, true);
  }
}

async function deleteProduct(productId) {
  if (!isAdmin()) {
    showToast("Для удаления товара нужно войти как администратор.");
    return;
  }

  const product = state.products.find((item) => item.id === productId);
  if (!product || !confirm(`Удалить товар "${product.name}"?`)) {
    return;
  }

  try {
    await requestJson(`/database/products/${productId}`, "DELETE");
    if (state.editingProductId === productId) {
      resetProductForm();
    }
    removeFromCart(productId);
    setAdminMessage("Товар удален");
    await loadData();
  } catch (error) {
    setAdminMessage(`Ошибка удаления товара: ${error.message}`, true);
  }
}

function renderError(error) {
  els.statsTitle.textContent = "API недоступен";
  els.categoriesCount.textContent = "0";
  els.productsCount.textContent = "0";
  els.specsCount.textContent = "0";
  els.categoryGrid.innerHTML = '<p class="empty">Не удалось загрузить категории.</p>';
  els.productGrid.innerHTML = "";
  els.emptyProducts.hidden = false;
  els.emptyProducts.textContent = `Не удалось загрузить товары: ${error.message}`;
}

function normalizeCart() {
  for (const [productId, quantity] of Object.entries(state.cart)) {
    const product = state.products.find((item) => item.id === Number(productId));
    if (!product || Number(product.quantity) <= 0) {
      delete state.cart[productId];
      continue;
    }
    state.cart[productId] = Math.min(quantity, Number(product.quantity));
  }
  saveCart();
}

async function loadEnumerationData() {
  try {
    const enumerations = await fetchJson("/database/enumerations");
    const enumDetails = await Promise.all(
      enumerations.map((enumeration) => fetchJson(`/database/enumerations/${enumeration.id}`)),
    );
    const values = {};
    for (const enumeration of enumDetails) {
      for (const item of enumeration.values ?? []) {
        if (item.item_type === "value" && item.value !== null) {
          values[String(item.id)] = item.value;
        } else if (item.item_type === "enum" && item.child_name !== null) {
          values[String(item.id)] = item.child_name;
        }
      }
    }
    return {
      enumerations,
      details: enumDetails,
      values,
    };
  } catch {
    return {
      enumerations: [],
      details: [],
      values: {},
    };
  }
}

function setAdminMessage(message, isError = false) {
  els.adminMessage.textContent = message;
  els.adminMessage.classList.toggle("is-error", isError);
}

function renderAuthState() {
  const adminMode = isAdmin();
  els.adminForms.hidden = !adminMode;
  els.loginForm.hidden = Boolean(state.auth);
  els.logoutButton.hidden = !state.auth;

  if (!state.auth) {
    els.authStatus.textContent = "Вы работаете в режиме просмотра.";
  } else if (adminMode) {
    els.authStatus.textContent = `Вход выполнен: ${state.auth.username}, роль администратора.`;
  } else {
    els.authStatus.textContent = `Вход выполнен: ${state.auth.username}, режим просмотра.`;
  }

  if (!adminMode) {
    resetCategoryForm();
    resetProductForm();
  }
}

function showToast(message) {
  els.toast.textContent = message;
  els.toast.hidden = false;
  window.clearTimeout(showToast.timeoutId);
  showToast.timeoutId = window.setTimeout(() => {
    els.toast.hidden = true;
  }, 4200);
}

function readDraftFilters() {
  return {
    query: els.searchInput.value.trim(),
    categoryId: els.categorySelect.value,
    minPrice: els.minPriceInput.value,
    maxPrice: els.maxPriceInput.value,
    inStockOnly: els.inStockInput.checked,
    specName: els.specFilterSelect.value,
    specValue: els.specValueInput.value.trim(),
    sortBy: els.sortSelect.value,
  };
}

function validateFilters(filters) {
  const errors = [];
  const minPrice = filters.minPrice === "" ? null : Number(filters.minPrice);
  const maxPrice = filters.maxPrice === "" ? null : Number(filters.maxPrice);

  if (filters.minPrice !== "" && !Number.isFinite(minPrice)) {
    errors.push("минимальная цена должна быть числом");
  }
  if (filters.maxPrice !== "" && !Number.isFinite(maxPrice)) {
    errors.push("максимальная цена должна быть числом");
  }
  if (minPrice !== null && minPrice < 0) {
    errors.push("минимальная цена не может быть отрицательной");
  }
  if (maxPrice !== null && maxPrice < 0) {
    errors.push("максимальная цена не может быть отрицательной");
  }
  if (minPrice !== null && maxPrice !== null && minPrice > maxPrice) {
    errors.push("нижняя граница цены не может быть больше верхней");
  }
  return errors.length ? `Нельзя применить фильтры: ${errors.join(", ")}.` : null;
}

function applyFilters() {
  const filters = readDraftFilters();
  const validationError = validateFilters(filters);
  if (validationError) {
    showToast(validationError);
    return;
  }

  state.draftFilters = { ...filters };
  state.appliedFilters = { ...filters };
  renderProducts();
}

async function loadData() {
  const [categories, products, enumData] = await Promise.all([
    fetchJson("/database/categories"),
    fetchJson("/database/products"),
    loadEnumerationData(),
  ]);

  state.categories = categories;
  state.products = products;
  state.enumerations = enumData.enumerations;
  state.enumerationDetails = enumData.details;
  state.enumValues = enumData.values;
  normalizeCart();

  renderStats();
  renderFilters();
  renderCategories();
  renderEnumerationControls();
  await renderCategoryParametersList();
  renderProducts();
  renderCart();
}

async function requestJson(url, method, payload = null) {
  const options = {
    method,
    headers: {
      ...getAuthHeaders(),
    },
  };

  if (payload !== null) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(payload);
  }

  return fetchJson(url, options);
}

async function submitJson(url, payload) {
  return fetchJson(url, {
    method: "POST",
    headers: {
      ...getAuthHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

function getProductPayload(product, overrides = {}) {
  return {
    name: product.name,
    price: Number(product.price),
    quantity: Number(product.quantity),
    description: product.description ?? null,
    specifications: (product.specifications ?? []).map((specification) => ({
      specification_id: specification.id,
    })),
    ...overrides,
  };
}

function resetCategoryForm() {
  state.editingCategoryId = null;
  els.categoryForm.reset();
  els.categoryFormTitle.textContent = "Новая категория";
  els.categorySubmitButton.textContent = "Создать категорию";
  els.categoryCancelButton.hidden = true;
  fillCategorySelect(els.parentCategorySelect, "Корневой раздел", true);
}

function resetProductForm() {
  state.editingProductId = null;
  els.productForm.reset();
  els.productFormTitle.textContent = "Новый товар";
  els.productSubmitButton.textContent = "Создать товар";
  els.productCancelButton.hidden = true;
  fillCategorySelect(els.productCategorySelect, "Выберите категорию");
  resetSpecRows();
}

function editCategory(categoryId) {
  const category = state.categories.find((item) => item.id === categoryId);
  if (!category) {
    return;
  }

  state.editingCategoryId = category.id;
  els.categoryForm.elements.name.value = category.name;
  els.parentCategorySelect.value = category.parent_id ? String(category.parent_id) : "";
  els.categoryFormTitle.textContent = `Редактирование категории #${category.id}`;
  els.categorySubmitButton.textContent = "Сохранить категорию";
  els.categoryCancelButton.hidden = false;
  document.querySelector("#admin").scrollIntoView({ behavior: "smooth" });
}

function editProduct(productId) {
  const product = state.products.find((item) => item.id === productId);
  if (!product) {
    return;
  }

  state.editingProductId = product.id;
  els.productForm.elements.name.value = product.name;
  els.productCategorySelect.value = String(product.category_id);
  els.productForm.elements.price.value = product.price;
  els.productForm.elements.quantity.value = product.quantity;
  els.productForm.elements.description.value = product.description ?? "";
  resetSpecRows(product.specifications ?? []);
  els.productFormTitle.textContent = `Редактирование товара #${product.id}`;
  els.productSubmitButton.textContent = "Сохранить товар";
  els.productCancelButton.hidden = false;
  document.querySelector("#admin").scrollIntoView({ behavior: "smooth" });
}

async function handleCategorySubmit(event) {
  event.preventDefault();
  if (!isAdmin()) {
    setAdminMessage("Для сохранения категории нужно войти как администратор.", true);
    return;
  }

  const formData = new FormData(els.categoryForm);
  const parentId = formData.get("parent_id");
  const currentCategory = state.categories.find((item) => item.id === state.editingCategoryId);
  const payload = {
    name: String(formData.get("name")).trim(),
    parent_id: parentId ? Number(parentId) : null,
  };

  try {
    if (currentCategory) {
      if (payload.parent_id === currentCategory.id) {
        throw new Error("Категория не может быть родителем самой себе");
      }
      if (payload.parent_id === null && currentCategory.parent_id !== null) {
        throw new Error("API пока не поддерживает перемещение категории в корень");
      }
      await requestJson(`/database/categories/${currentCategory.id}`, "PATCH", {
        name: payload.name,
      });
      if (payload.parent_id && payload.parent_id !== currentCategory.parent_id) {
        await requestJson(`/database/categories/${currentCategory.id}/move`, "PATCH", {
          new_parent_id: payload.parent_id,
        });
      }
      resetCategoryForm();
      setAdminMessage("Категория обновлена");
    } else {
      await submitJson("/database/categories", payload);
      resetCategoryForm();
      setAdminMessage("Категория создана");
    }
    await loadData();
  } catch (error) {
    setAdminMessage(`Ошибка сохранения категории: ${error.message}`, true);
  }
}

async function handleProductSubmit(event) {
  event.preventDefault();
  if (!isAdmin()) {
    setAdminMessage("Для сохранения товара нужно войти как администратор.", true);
    return;
  }

  const formData = new FormData(els.productForm);
  const description = String(formData.get("description")).trim();
  const currentProduct = state.products.find((item) => item.id === state.editingProductId);
  let specifications = [];
  try {
    specifications = readProductSpecifications();
  } catch (error) {
    setAdminMessage(`Ошибка характеристик товара: ${error.message}`, true);
    return;
  }
  const payload = {
    name: String(formData.get("name")).trim(),
    category_id: Number(formData.get("category_id")),
    price: Number(formData.get("price")),
    quantity: Number(formData.get("quantity")),
    description: description || null,
    specifications,
  };

  try {
    if (currentProduct) {
      await requestJson(
        `/database/products/${currentProduct.id}`,
        "PATCH",
        getProductPayload(currentProduct, {
          name: payload.name,
          price: payload.price,
          quantity: payload.quantity,
          description: payload.description,
          specifications: payload.specifications,
        }),
      );
      if (payload.category_id !== currentProduct.category_id) {
        await requestJson(`/database/products/${currentProduct.id}/move`, "PATCH", {
          new_category_id: payload.category_id,
        });
      }
      resetProductForm();
      setAdminMessage("Товар обновлен");
    } else {
      await submitJson("/database/products", payload);
      resetProductForm();
      setAdminMessage("Товар создан");
    }
    await loadData();
  } catch (error) {
    setAdminMessage(`Ошибка сохранения товара: ${error.message}`, true);
  }
}

async function handleEnumerationSubmit(event) {
  event.preventDefault();
  if (!isAdmin()) {
    setAdminMessage("Для создания перечисления нужно войти как администратор.", true);
    return;
  }
  const formData = new FormData(els.enumerationForm);
  const description = String(formData.get("description")).trim();
  try {
    await submitJson("/database/enumerations", {
      name: String(formData.get("name")).trim(),
      description: description || null,
    });
    els.enumerationForm.reset();
    setAdminMessage("Перечисление создано");
    await loadData();
  } catch (error) {
    setAdminMessage(`Ошибка создания перечисления: ${error.message}`, true);
  }
}

async function handleEnumValueSubmit(event) {
  event.preventDefault();
  if (!isAdmin()) {
    setAdminMessage("Для добавления значения нужно войти как администратор.", true);
    return;
  }
  const formData = new FormData(els.enumValueForm);
  const enumId = Number(formData.get("enum_id"));
  const itemType = String(formData.get("item_type"));
  const description = String(formData.get("description")).trim();
  const payload = {
    item_type: itemType,
    value: null,
    child_enum_id: null,
    priority: Number(formData.get("priority") || 0),
    description: description || null,
  };

  if (itemType === "enum") {
    payload.child_enum_id = Number(formData.get("child_enum_id"));
  } else {
    payload.value = String(formData.get("value")).trim();
  }

  try {
    await submitJson(`/database/enumerations/${enumId}/values`, payload);
    const selectedEnumId = els.enumValueEnumSelect.value;
    els.enumValueForm.reset();
    els.enumValueEnumSelect.value = selectedEnumId;
    toggleEnumValueMode();
    setAdminMessage("Значение перечисления добавлено");
    await loadData();
    els.enumValueEnumSelect.value = selectedEnumId;
    renderEnumerationControls();
  } catch (error) {
    setAdminMessage(`Ошибка добавления значения: ${error.message}`, true);
  }
}

async function handleParameterSubmit(event) {
  event.preventDefault();
  if (!isAdmin()) {
    setAdminMessage("Для назначения параметра нужно войти как администратор.", true);
    return;
  }
  const formData = new FormData(els.parameterForm);
  const parameterType = String(formData.get("parameter_type"));
  const categoryId = Number(formData.get("category_id"));
  const code = String(formData.get("code")).trim();
  const description = null;
  const enumId = formData.get("enum_id");
  const minValue = formData.get("min_value");
  const maxValue = formData.get("max_value");

  try {
    const parameter = await submitJson("/database/parameters", {
      code,
      name: String(formData.get("name")).trim(),
      description,
      parameter_type: parameterType,
      unit_id: null,
      enum_id: parameterType === "enum" ? Number(enumId) : null,
    });
    await submitJson(`/database/categories/${categoryId}/parameters`, {
      parameter_id: parameter.id,
      priority: Number(formData.get("priority") || 0),
      is_required: formData.get("is_required") === "on",
      min_value: minValue === "" ? null : Number(minValue),
      max_value: maxValue === "" ? null : Number(maxValue),
    });
    const selectedCategoryId = els.parameterCategorySelect.value;
    els.parameterForm.reset();
    els.parameterCategorySelect.value = selectedCategoryId;
    toggleParameterEnumMode();
    setAdminMessage("Параметр создан и назначен категории. Потомки получили его как унаследованный.");
    await renderCategoryParametersList();
  } catch (error) {
    setAdminMessage(`Ошибка назначения параметра: ${error.message}`, true);
  }
}

function toggleEnumValueMode() {
  const enumMode = els.enumItemTypeSelect.value === "enum";
  els.enumValueTextWrap.hidden = enumMode;
  els.enumChildWrap.hidden = !enumMode;
}

function toggleParameterEnumMode() {
  els.parameterEnumWrap.hidden = els.parameterTypeSelect.value !== "enum";
}

async function handleCardAction(event) {
  const button = event.target.closest("[data-action]");
  if (!button) {
    return;
  }

  event.stopPropagation();
  const id = Number(button.dataset.id);
  if (
    ["edit-category", "delete-category", "edit-product", "delete-product"].includes(button.dataset.action)
    && !isAdmin()
  ) {
    showToast("Для редактирования данных нужно войти как администратор.");
    return;
  }

  if (button.dataset.action === "edit-category") {
    editCategory(id);
  } else if (button.dataset.action === "delete-category") {
    await deleteCategory(id);
  } else if (button.dataset.action === "add-to-cart") {
    addToCart(id);
  } else if (button.dataset.action === "edit-product") {
    editProduct(id);
  } else if (button.dataset.action === "delete-product") {
    await deleteProduct(id);
  } else if (button.dataset.action === "increase-cart") {
    setCartQuantity(id, getCartQuantity(id) + 1);
  } else if (button.dataset.action === "decrease-cart") {
    const nextQuantity = getCartQuantity(id) - 1;
    if (nextQuantity <= 0) {
      removeFromCart(id);
    } else {
      setCartQuantity(id, nextQuantity);
    }
  } else if (button.dataset.action === "remove-from-cart") {
    removeFromCart(id);
  } else if (button.dataset.action === "remove-spec-row") {
    button.closest(".spec-row")?.remove();
    if (els.specRows.children.length === 0) {
      addSpecRow();
    }
  }
}

async function handleLoginSubmit(event) {
  event.preventDefault();
  const formData = new FormData(els.loginForm);
  const payload = {
    username: String(formData.get("username")).trim(),
    password: String(formData.get("password")),
  };

  try {
    const response = await fetchJson("/auth/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    state.auth = {
      accessToken: response.access_token,
      username: response.username,
      role: response.role,
      expiresAt: Date.now() + Number(response.expires_in) * 1000,
    };
    saveAuth(state.auth);
    els.loginForm.reset();
    renderAuthState();
    renderCategories();
    renderProducts();
    setAdminMessage(
      isAdmin()
        ? "Вход выполнен. Доступно редактирование данных."
        : "Вход выполнен. Доступен режим просмотра.",
    );
  } catch (error) {
    setAdminMessage(`Ошибка входа: ${error.message}`, true);
  }
}

function handleLogout() {
  state.auth = null;
  saveAuth(null);
  renderAuthState();
  renderCategories();
  renderProducts();
  setAdminMessage("Вы вышли из режима администратора.");
}

function handleCartInput(event) {
  const input = event.target.closest('[data-action="set-cart"]');
  if (!input) {
    return;
  }

  setCartQuantity(Number(input.dataset.id), Number(input.value));
}

function resetFilters() {
  const emptyFilters = {
    query: "",
    categoryId: "",
    minPrice: "",
    maxPrice: "",
    inStockOnly: false,
    specName: "",
    specValue: "",
    sortBy: "default",
  };

  state.draftFilters = { ...emptyFilters };
  state.appliedFilters = { ...emptyFilters };

  els.searchInput.value = "";
  els.categorySelect.value = "";
  els.minPriceInput.value = "";
  els.maxPriceInput.value = "";
  els.inStockInput.checked = false;
  els.specFilterSelect.value = "";
  els.specValueInput.value = "";
  els.sortSelect.value = "default";
  renderProducts();
}

async function init() {
  renderAuthState();
  try {
    await loadData();
    renderAuthState();
  } catch (error) {
    renderError(error);
  }
}

els.applyFiltersButton.addEventListener("click", applyFilters);
els.resetFiltersButton.addEventListener("click", resetFilters);
els.loginForm.addEventListener("submit", handleLoginSubmit);
els.logoutButton.addEventListener("click", handleLogout);
els.categoryForm.addEventListener("submit", handleCategorySubmit);
els.productForm.addEventListener("submit", handleProductSubmit);
els.enumerationForm.addEventListener("submit", handleEnumerationSubmit);
els.enumValueForm.addEventListener("submit", handleEnumValueSubmit);
els.parameterForm.addEventListener("submit", handleParameterSubmit);
els.categoryCancelButton.addEventListener("click", resetCategoryForm);
els.productCancelButton.addEventListener("click", resetProductForm);
els.addSpecButton.addEventListener("click", () => addSpecRow());
els.enumValueEnumSelect.addEventListener("change", renderEnumerationControls);
els.enumItemTypeSelect.addEventListener("change", toggleEnumValueMode);
els.parameterCategorySelect.addEventListener("change", renderCategoryParametersList);
els.parameterTypeSelect.addEventListener("change", toggleParameterEnumMode);
els.clearCartButton.addEventListener("click", clearCart);
els.checkoutButton.addEventListener("click", () => {
  showToast("Оформление заказа пока не реализовано.");
});
els.cartItems.addEventListener("change", handleCartInput);
document.addEventListener("click", handleCardAction);

init();
