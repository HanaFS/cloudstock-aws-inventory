const ProductsModule = (() => {
  // State quản lý danh sách
  let productList = [];
  let supplierList = [];
  let filterSearch = "";
  let filterCategory = "ALL";
  let filterStockStatus = "ALL"; // ALL | SAFE | LOW
  let currentPage = 1;
  const pageSize = 8;

  let editingProductId = null;
  let deletingProductId = null;
  let uploadedImageBase64 = "";

   async function loadProducts() {
    try {
      const [prodRes, supRes] = await Promise.all([
        ApiService.Products.getAll(),
        ApiService.Suppliers.getAll(),
      ]);
      productList = prodRes.data || [];
      supplierList = supRes.data || [];
      renderCategoryFilterOptions();
      renderSupplierOptionsInForm();
      renderProductTable();
    } catch (err) {
      console.error("Loi tai danh sach san pham:", err);
      if (window.AuthModule) {
        AuthModule.showToast("Loi tai hang hoa: " + err.message, "error");
      }
    }
  }

  function getFilteredProducts() {
    return productList.filter((p) => {
      // 1. Tìm kiếm text
      const searchMatch =
        !filterSearch ||
        (p.name && p.name.toLowerCase().includes(filterSearch)) ||
        (p.productId && p.productId.toLowerCase().includes(filterSearch));

      // 2. Lọc Category
      const catMatch =
        filterCategory === "ALL" || p.category === filterCategory;

      // 3. Lọc Trạng thái tồn kho
      let stockMatch = true;
      if (filterStockStatus === "LOW") {
        stockMatch = (p.quantity || 0) < (p.minThreshold || 0);
      } else if (filterStockStatus === "SAFE") {
        stockMatch = (p.quantity || 0) >= (p.minThreshold || 0);
      }

      return searchMatch && catMatch && stockMatch;
    });
  }

    function renderProductTable() {
    const tbody = document.getElementById("product-table-body");
    const countBadge = document.getElementById("product-total-badge");
    const paginationEl = document.getElementById("product-pagination");
    if (!tbody) return;

    const filtered = getFilteredProducts();

    if (countBadge) {
      countBadge.textContent = `${filtered.length} san pham`;
    }

    const totalPages = Math.ceil(filtered.length / pageSize) || 1;
    if (currentPage > totalPages) currentPage = totalPages;
    const startIdx = (currentPage - 1) * pageSize;
    const pagedItems = filtered.slice(startIdx, startIdx + pageSize);

    if (pagedItems.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="8" class="col-c text-muted cell-padded-lg">
            Khong tim thay san pham nao phu hop voi bo loc.
          </td>
        </tr>
      `;
      if (paginationEl) paginationEl.innerHTML = "";
      return;
    }

    const supMap = {};
    supplierList.forEach((s) => {
      supMap[s.supplierId] = s.name;
    });

    tbody.innerHTML = pagedItems
      .map((p) => {
        const isLow = (p.quantity || 0) < (p.minThreshold || 0);
        const stockBadge = isLow
          ? `<span class="badge badge-danger">DUOI NGUONG</span>`
          : `<span class="badge badge-success">AN TOAN</span>`;
        const supName = supMap[p.supplierId] || "Chua gan NCC";

        return `
          <tr>
            <td class="col-mono"><strong>${p.productId}</strong></td>
            <td>
              <div><strong>${p.name}</strong></div>
              ${p.imageUrl ? `<span class="text-muted text-xs">Co anh minh hoa (S3)</span>` : ""}
            </td>
            <td><span class="badge badge-neutral">${p.category}</span></td>
            <td class="col-r font-mono">${formatCurrency(p.price)}</td>
            <td class="col-r ${isLow ? "text-danger" : ""}">
              <strong>${formatNumber(p.quantity)}</strong>
            </td>
            <td class="col-r text-muted">${formatNumber(p.minThreshold)}</td>
            <td>${stockBadge}</td>
            <td class="col-actions">
              <button
                type="button"
                class="btn btn-secondary btn-sm"
                onclick="ProductsModule.openEditModal('${p.productId}')"
              >
                Sua
              </button>
              <button
                type="button"
                class="btn btn-danger btn-sm"
                onclick="ProductsModule.confirmDelete('${p.productId}')"
              >
                Xoa
              </button>
            </td>
          </tr>
        `;
      })
      .join("");

    renderPagination(paginationEl, totalPages, filtered.length);
  }

  function renderPagination(el, totalPages, totalItems) {
    if (!el) return;
    if (totalPages <= 1) {
      el.innerHTML = `
        <div class="pagination-info">Hien thi ${totalItems} ket qua</div>
      `;
      return;
    }

    let btns = `
      <div class="pagination-info">Trang ${currentPage} / ${totalPages} (${totalItems} ket qua)</div>
      <button
        type="button"
        class="page-btn"
        ${currentPage === 1 ? "disabled" : ""}
        onclick="ProductsModule.changePage(${currentPage - 1})"
      >
        Truoc
      </button>
    `;

    for (let p = 1; p <= totalPages; p++) {
      btns += `
        <button
          type="button"
          class="page-btn ${p === currentPage ? "active" : ""}"
          onclick="ProductsModule.changePage(${p})"
        >
          ${p}
        </button>
      `;
    }

    btns += `
      <button
        type="button"
        class="page-btn"
        ${currentPage === totalPages ? "disabled" : ""}
        onclick="ProductsModule.changePage(${currentPage + 1})"
      >
        Sau
      </button>
    `;

    el.innerHTML = btns;
  }

  function changePage(p) {
    currentPage = p;
    renderProductTable();
  }

  function renderCategoryFilterOptions() {
    const select = document.getElementById("filter-product-category");
    if (!select) return;

    const categories = Array.from(
      new Set(productList.map((p) => p.category).filter(Boolean))
    );

    let html = `<option value="ALL">Tat ca danh muc</option>`;
    categories.forEach((cat) => {
      html += `<option value="${cat}">${cat}</option>`;
    });
    select.innerHTML = html;
  }

  function renderSupplierOptionsInForm() {
    const select = document.getElementById("prod-form-supplier");
    if (!select) return;

    let html = `<option value="">-- Chon nha cung cap --</option>`;
    supplierList.forEach((s) => {
      html += `<option value="${s.supplierId}">${s.name} (${s.supplierId})</option>`;
    });
    select.innerHTML = html;
  }

  function openCreateModal() {
    editingProductId = null;
    uploadedImageBase64 = "";

    const form = document.getElementById("form-product");
    const title = document.getElementById("modal-product-title");
    const dropzoneText = document.getElementById("prod-dropzone-text");

    if (form) form.reset();
    if (title) title.textContent = "Them Hang hoa Moi";
    if (dropzoneText) dropzoneText.textContent = "Keo tha tep vao day hoac bam de chon anh minh hoa (Mo phong S3 Upload)";

    const idInput = document.getElementById("prod-form-id");
    if (idInput) {
      idInput.value = "prod-" + String(productList.length + 1).padStart(3, "0");
      idInput.readOnly = false;
    }

    const modal = document.getElementById("modal-product");
    if (modal) modal.classList.add("visible");
  }

  function openEditModal(productId) {
    const prod = productList.find((p) => p.productId === productId);
    if (!prod) return;

    editingProductId = productId;
    uploadedImageBase64 = prod.imageUrl || "";

    const title = document.getElementById("modal-product-title");
    const idInput = document.getElementById("prod-form-id");
    const nameInput = document.getElementById("prod-form-name");
    const catInput = document.getElementById("prod-form-category");
    const priceInput = document.getElementById("prod-form-price");
    const qtyInput = document.getElementById("prod-form-quantity");
    const minInput = document.getElementById("prod-form-min");
    const supSelect = document.getElementById("prod-form-supplier");
    const dropzoneText = document.getElementById("prod-dropzone-text");

    if (title) title.textContent = `Chinh sua: ${prod.productId}`;
    if (idInput) {
      idInput.value = prod.productId;
      idInput.readOnly = true; // Không sửa mã khi edit
    }
    if (nameInput) nameInput.value = prod.name || "";
    if (catInput) catInput.value = prod.category || "";
    if (priceInput) priceInput.value = prod.price || 0;
    if (qtyInput) qtyInput.value = prod.quantity || 0;
    if (minInput) minInput.value = prod.minThreshold || 0;
    if (supSelect) supSelect.value = prod.supplierId || "";
    if (dropzoneText) {
      dropzoneText.textContent = prod.imageUrl
        ? "Da co anh tai len tren S3. Keo anh moi neu muon thay the."
        : "Keo tha tep vao day hoac bam de chon anh (S3 Upload)";
    }

    const modal = document.getElementById("modal-product");
    if (modal) modal.classList.add("visible");
  }

  function closeModal() {
    const modal = document.getElementById("modal-product");
    if (modal) modal.classList.remove("visible");
    editingProductId = null;
    uploadedImageBase64 = "";
  }

  async function handleFormSubmit(e) {
    e.preventDefault();

    const productId = document.getElementById("prod-form-id")?.value.trim();
    const name = document.getElementById("prod-form-name")?.value.trim();
    const category = document.getElementById("prod-form-category")?.value.trim();
    const price = Number(document.getElementById("prod-form-price")?.value) || 0;
    const quantity = Number(document.getElementById("prod-form-quantity")?.value) || 0;
    const minThreshold = Number(document.getElementById("prod-form-min")?.value) || 0;
    const supplierId = document.getElementById("prod-form-supplier")?.value || null;

    if (!productId || !name || !category) {
      if (window.AuthModule) {
        AuthModule.showToast("Vui long nhap day du thong tin bat buoc", "warning");
      }
      return;
    }

    const payload = {
      productId,
      name,
      category,
      price,
      quantity,
      minThreshold,
      supplierId,
      imageUrl: uploadedImageBase64,
      updatedAt: new Date().toISOString(),
    };

    try {
      if (editingProductId) {
        // Cập nhật
        await ApiService.Products.update(editingProductId, payload);
        if (window.AuthModule) {
          AuthModule.showToast(`Da cap nhat hang hoa: ${name}`, "success");
        }
      } else {
        // Kiểm tra trùng mã
        const existing = productList.find((p) => p.productId === productId);
        if (existing) {
          if (window.AuthModule) {
            AuthModule.showToast(`Ma san pham ${productId} da ton tai`, "error");
          }
          return;
        }
        await ApiService.Products.create(payload);
        if (window.AuthModule) {
          AuthModule.showToast(`Them moi thanh cong: ${name}`, "success");
        }
      }

      closeModal();
      await loadProducts();

      if (window.DashboardModule) {
        DashboardModule.renderDashboard();
      }
    } catch (err) {
      if (window.AuthModule) {
        AuthModule.showToast(`Loi: ${err.message}`, "error");
      }
    }
  }

  function confirmDelete(productId) {
    const prod = productList.find((p) => p.productId === productId);
    if (!prod) return;

    deletingProductId = productId;
    const msgEl = document.getElementById("confirm-delete-msg");
    if (msgEl) {
      msgEl.textContent = `Ban co chac chan muon xoa hang hoa "${prod.name}" (Ma: ${prod.productId})? Thao tac nay se cap nhat truc tiep vao DynamoDB va khong the hoan tac.`;
    }

    const modal = document.getElementById("modal-confirm-delete-product");
    if (modal) modal.classList.add("visible");
  }

  function closeDeleteModal() {
    const modal = document.getElementById("modal-confirm-delete-product");
    if (modal) modal.classList.remove("visible");
    deletingProductId = null;
  }

  async function executeDelete() {
    if (!deletingProductId) return;

    try {
      await ApiService.Products.delete(deletingProductId);
      if (window.AuthModule) {
        AuthModule.showToast("Da xoa hang hoa thanh cong", "success");
      }
      closeDeleteModal();
      await loadProducts();

      if (window.DashboardModule) {
        DashboardModule.renderDashboard();
      }
    } catch (err) {
      if (window.AuthModule) {
        AuthModule.showToast(`Loi xoa hang hoa: ${err.message}`, "error");
      }
    }
  }

 
  function setupDropzone() {
    const dropzone = document.getElementById("prod-dropzone");
    const fileInput = document.getElementById("prod-file-input");
    const dropzoneText = document.getElementById("prod-dropzone-text");
    if (!dropzone || !fileInput) return;

    dropzone.addEventListener("click", () => fileInput.click());

    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });

    dropzone.addEventListener("dragleave", () => {
      dropzone.classList.remove("dragover");
    });

    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        handleFileSelect(e.dataTransfer.files[0]);
      }
    });

    fileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        handleFileSelect(e.target.files[0]);
      }
    });

    function handleFileSelect(file) {
      if (!file.type.startsWith("image/")) {
        if (window.AuthModule) {
          AuthModule.showToast("Vui long chi chon tep hinh anh", "warning");
        }
        return;
      }

      const reader = new FileReader();
      reader.onload = (evt) => {
        uploadedImageBase64 = evt.target.result;
        if (dropzoneText) {
          dropzoneText.textContent = `Da chon tep: ${file.name} (${(file.size / 1024).toFixed(1)} KB) - San sang day len S3`;
        }
        if (window.AuthModule) {
          AuthModule.showToast(`Da nap anh ${file.name} vao phieu`, "info");
        }
      };
      reader.readAsDataURL(file);
    }
  }

    function setupFilters() {
    const searchInput = document.getElementById("search-product-input");
    const catSelect = document.getElementById("filter-product-category");
    const stockSelect = document.getElementById("filter-product-stock");

    if (searchInput) {
      searchInput.addEventListener("input", window.debounce((e) => {
        filterSearch = e.target.value.trim().toLowerCase();
        currentPage = 1;
        renderProductTable();
      }, 300));
    }

    if (catSelect) {
      catSelect.addEventListener("change", (e) => {
        filterCategory = e.target.value;
        currentPage = 1;
        renderProductTable();
      });
    }

    if (stockSelect) {
      stockSelect.addEventListener("change", (e) => {
        filterStockStatus = e.target.value;
        currentPage = 1;
        renderProductTable();
      });
    }
  }

  
  function formatCurrency(n) {
    if (typeof n !== "number" || isNaN(n)) return "0 d";
    return new Intl.NumberFormat("vi-VN").format(n) + " d";
  }

  function formatNumber(n) {
    if (typeof n !== "number" || isNaN(n)) return "0";
    return new Intl.NumberFormat("vi-VN").format(n);
  }

  
  function init() {
    setupFilters();
    setupDropzone();

    const form = document.getElementById("form-product");
    if (form) form.addEventListener("submit", handleFormSubmit);

    const btnExecDelete = document.getElementById("btn-exec-delete-product");
    if (btnExecDelete) btnExecDelete.addEventListener("click", executeDelete);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  /* Public API */
  return {
    init,
    loadProducts,
    changePage,
    openCreateModal,
    openEditModal,
    closeModal,
    confirmDelete,
    closeDeleteModal,
  };
})();

