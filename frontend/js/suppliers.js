 const SuppliersModule = (() => {
   
  let supplierList = [];
  let productList = [];
  let filterSearch = "";
  let editingSupplierId = null;
  let deletingSupplierId = null;

  async function loadSuppliers() {
    try {
      const [supRes, prodRes] = await Promise.all([
        ApiService.Suppliers.getAll(),
        ApiService.Products.getAll(),
      ]);
      supplierList = supRes.data || [];
      productList = prodRes.data || [];
      renderSupplierTable();
    } catch (err) {
      console.error("Loi tai nha cung cap:", err);
      if (window.AuthModule) {
        AuthModule.showToast("Loi tai nha cung cap: " + err.message, "error");
      }
    }
  }

  function getFilteredSuppliers() {
    return supplierList.filter((s) => {
      if (!filterSearch) return true;
      const q = filterSearch.toLowerCase();
      return (
        (s.name && s.name.toLowerCase().includes(q)) ||
        (s.supplierId && s.supplierId.toLowerCase().includes(q)) ||
        (s.phone && s.phone.toLowerCase().includes(q)) ||
        (s.address && s.address.toLowerCase().includes(q))
      );
    });
  }

   


  function renderSupplierTable() {
    const tbody = document.getElementById("supplier-table-body");
    const countBadge = document.getElementById("supplier-total-badge");
    if (!tbody) return;

    const filtered = getFilteredSuppliers();

    if (countBadge) {
      countBadge.textContent = `${filtered.length} doi tac`;
    }

    if (filtered.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" class="col-c text-muted cell-padded-lg">
            Khong tim thay nha cung cap nao phu hop voi tu khoa tim kiem.
          </td>
        </tr>
      `;
      return;
    }

     
    const productCountMap = {};
    productList.forEach((p) => {
      if (p.supplierId) {
        productCountMap[p.supplierId] = (productCountMap[p.supplierId] || 0) + 1;
      }
    });

    tbody.innerHTML = filtered
      .map((s) => {
        const prodCount = productCountMap[s.supplierId] || 0;
        const countBadgeHtml =
          prodCount > 0
            ? `<span class="badge badge-info">${prodCount} san pham</span>`
            : `<span class="badge badge-neutral">Chua co</span>`;

        return `
          <tr>
            <td class="col-mono"><strong>${s.supplierId}</strong></td>
            <td><strong>${s.name}</strong></td>
            <td class="col-mono">${s.phone || "-"}</td>
            <td>${s.address || "-"}</td>
            <td>${countBadgeHtml}</td>
            <td class="col-actions">
              <button
                type="button"
                class="btn btn-secondary btn-sm"
                onclick="SuppliersModule.openEditModal('${s.supplierId}')"
              >
                Sua
              </button>
              <button
                type="button"
                class="btn btn-danger btn-sm"
                onclick="SuppliersModule.confirmDelete('${s.supplierId}')"
              >
                Xoa
              </button>
            </td>
          </tr>
        `;
      })
      .join("");
  }

   


  function openCreateModal() {
    editingSupplierId = null;
    const form = document.getElementById("form-supplier");
    const title = document.getElementById("modal-supplier-title");

    if (form) form.reset();
    if (title) title.textContent = "Them Nha Cung Cap Moi";

     
    const idInput = document.getElementById("sup-form-id");
    if (idInput) {
      idInput.value = "sup-" + String(supplierList.length + 1).padStart(3, "0");
      idInput.readOnly = false;
    }

    const modal = document.getElementById("modal-supplier");
    if (modal) modal.classList.add("visible");
  }

  function openEditModal(supplierId) {
    const sup = supplierList.find((s) => s.supplierId === supplierId);
    if (!sup) return;

    editingSupplierId = supplierId;
    const title = document.getElementById("modal-supplier-title");
    const idInput = document.getElementById("sup-form-id");
    const nameInput = document.getElementById("sup-form-name");
    const phoneInput = document.getElementById("sup-form-phone");
    const addressInput = document.getElementById("sup-form-address");

    if (title) title.textContent = `Chinh sua: ${sup.supplierId}`;
    if (idInput) {
      idInput.value = sup.supplierId;
      idInput.readOnly = true;
    }
    if (nameInput) nameInput.value = sup.name || "";
    if (phoneInput) phoneInput.value = sup.phone || "";
    if (addressInput) addressInput.value = sup.address || "";

    const modal = document.getElementById("modal-supplier");
    if (modal) modal.classList.add("visible");
  }

  function closeModal() {
    const modal = document.getElementById("modal-supplier");
    if (modal) modal.classList.remove("visible");
    editingSupplierId = null;
  }

  async function handleFormSubmit(e) {
    e.preventDefault();

    const supplierId = document.getElementById("sup-form-id")?.value.trim();
    const name = document.getElementById("sup-form-name")?.value.trim();
    const phone = document.getElementById("sup-form-phone")?.value.trim();
    const address = document.getElementById("sup-form-address")?.value.trim();

    if (!supplierId || !name) {
      if (window.AuthModule) {
        AuthModule.showToast("Vui long nhap Ma NCC va Ten cong ty", "warning");
      }
      return;
    }

    const payload = { supplierId, name, phone, address };

    try {
      if (editingSupplierId) {
        await ApiService.Suppliers.update(editingSupplierId, payload);
        if (window.AuthModule) {
          AuthModule.showToast(`Da cap nhat nha cung cap: ${name}`, "success");
        }
      } else {
        const existing = supplierList.find((s) => s.supplierId === supplierId);
        if (existing) {
          if (window.AuthModule) {
            AuthModule.showToast(`Ma NCC ${supplierId} da ton tai`, "error");
          }
          return;
        }
        await ApiService.Suppliers.create(payload);
        if (window.AuthModule) {
          AuthModule.showToast(`Them NCC thanh cong: ${name}`, "success");
        }
      }

      closeModal();
      await loadSuppliers();
    } catch (err) {
      if (window.AuthModule) {
        AuthModule.showToast(`Loi: ${err.message}`, "error");
      }
    }
  }

   


  function confirmDelete(supplierId) {
    const sup = supplierList.find((s) => s.supplierId === supplierId);
    if (!sup) return;

     
    const linkedProducts = productList.filter((p) => p.supplierId === supplierId);
    if (linkedProducts.length > 0) {
      const prodNames = linkedProducts
        .slice(0, 3)
        .map((p) => `${p.name} (${p.productId})`)
        .join(", ");
      const moreText = linkedProducts.length > 3 ? ` va ${linkedProducts.length - 3} mat hang khac` : "";

      if (window.AuthModule) {
        AuthModule.showToast(
          `Khong the xoa! Nha cung cap nay dang lien ket voi ${linkedProducts.length} mat hang: ${prodNames}${moreText}. Hay chuyen hoac xoa cac san pham tren truoc.`,
          "error"
        );
      }
      return;
    }

     
    deletingSupplierId = supplierId;
    const msgEl = document.getElementById("confirm-delete-supplier-msg");
    if (msgEl) {
      msgEl.textContent = `Ban co chac chan muon xoa Nha cung cap "${sup.name}" (Ma: ${sup.supplierId})? Thao tac nay se cap nhat vao DynamoDB va khong the hoan tac.`;
    }

    const modal = document.getElementById("modal-confirm-delete-supplier");
    if (modal) modal.classList.add("visible");
  }

  function closeDeleteModal() {
    const modal = document.getElementById("modal-confirm-delete-supplier");
    if (modal) modal.classList.remove("visible");
    deletingSupplierId = null;
  }

  async function executeDelete() {
    if (!deletingSupplierId) return;

    try {
      await ApiService.Suppliers.delete(deletingSupplierId);
      if (window.AuthModule) {
        AuthModule.showToast("Da xoa nha cung cap thanh cong", "success");
      }
      closeDeleteModal();
      await loadSuppliers();
    } catch (err) {
      if (window.AuthModule) {
        AuthModule.showToast(`Loi xoa nha cung cap: ${err.message}`, "error");
      }
    }
  }

   


  function setupFilters() {
    const searchInput = document.getElementById("search-supplier-input");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        filterSearch = e.target.value.trim().toLowerCase();
        renderSupplierTable();
      });
    }
  }

   


  function init() {
    setupFilters();

    const form = document.getElementById("form-supplier");
    if (form) form.addEventListener("submit", handleFormSubmit);

    const btnExecDelete = document.getElementById("btn-exec-delete-supplier");
    if (btnExecDelete) btnExecDelete.addEventListener("click", executeDelete);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

   
  return {
    init,
    loadSuppliers,
    openCreateModal,
    openEditModal,
    closeModal,
    confirmDelete,
    closeDeleteModal,
  };
})();
