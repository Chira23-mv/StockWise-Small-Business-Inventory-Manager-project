document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".flash-close").forEach((button) => {
    button.addEventListener("click", () => button.closest(".flash")?.remove());
  });

  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm || "Are you sure?")) event.preventDefault();
    });
  });

  const productSelect = document.querySelector('select[name="product_id"]');
  const movementSelect = document.querySelector('select[name="movement_type"]');
  const priceInput = document.querySelector('input[name="unit_price"]');
  const hint = document.querySelector("#stock-hint");

  function updateStockHint() {
    if (!productSelect || !hint) return;
    const option = productSelect.selectedOptions[0];
    if (!option || !option.value) {
      hint.textContent = "Choose a product to view its current quantity.";
      return;
    }
    hint.textContent = `Currently in stock: ${option.dataset.qty} units.`;
    if (priceInput && !priceInput.dataset.userEdited) {
      priceInput.value = movementSelect?.value === "OUT" ? option.dataset.selling : option.dataset.cost;
    }
  }
  if (priceInput) priceInput.addEventListener("input", () => { priceInput.dataset.userEdited = "true"; });
  if (productSelect) productSelect.addEventListener("change", () => {
    if (priceInput) delete priceInput.dataset.userEdited;
    updateStockHint();
  });
  if (movementSelect) movementSelect.addEventListener("change", () => {
    if (priceInput) delete priceInput.dataset.userEdited;
    updateStockHint();
  });
  updateStockHint();
});
