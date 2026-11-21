const InventoryModule = (() => {
   
  let productList = [];
  let supplierList = [];
  let currentSubTab = "in";  
  let attachedInvoiceName = "";
  let attachedInvoiceData = "";

   


  async function loadData() {
    try {
      const [prodRes, supRes] = await Promise.all([
        ApiService.Products.getAll(),
        ApiService.Suppliers.getAll(),
      ]);

      productList = prodRes.data || [];
      supplierList = supRes.data || [];

      populateDropdowns();
      renderRecentTransactions();

       
      checkPrefillFromDashboard();
    } catch (err) {
      console.error("Loi tai du lieu kho:", err);
      if (window.AuthModule) {
        AuthModule.showToast("Loi tai du lieu nghiep vu kho: " + err.message, "error");
      }
    }
  }

  function populateDropdowns() {
    const inProdSelect = document.getElementById("inv-in-product");
    const outProdSelect = document.getElementById("inv-out-product");
    const supSelect = document.getElementById("inv-in-supplier");

     
    let inProdHtml = `<option value="">-- Chon san pham nhap --</option>`;
     
    let outProdHtml = `<option value="">-- Chon san pham xuat --</option>`;

    productList.forEach((p) => {
      const isLow = (p.quantity || 0) < (p.minThreshold || 0);
      const tag = isLow ? " [DUOI NGUONG]" : "";
      inProdHtml += `<option value="${p.productId}">${p.productId} - ${p.name} (Ton hien tai: ${p.quantity})${tag}</option>`;
      outProdHtml += `<option value="${p.productId}">${p.productId} - ${p.name} (Kha dung: ${p.quantity})${tag}</option>`;
    });

    if (inProdSelect) inProdSelect.innerHTML = inProdHtml;
    if (outProdSelect) outProdSelect.innerHTML = outProdHtml;

     
    if (supSelect) {
      let supHtml = `<option value="">-- Chon nha cung cap --</option>`;
      supplierList.forEach((s) => {
        supHtml += `<option value="${s.supplierId}">${s.name} (${s.supplierId})</option>`;
      });
      supSelect.innerHTML = supHtml;
    }
  }

  function checkPrefillFromDashboard() {
    const prefillId = sessionStorage.getItem("cloudstock_prefill_product_id");
    if (!prefillId) return;

    switchSubTab("in");
    const inProdSelect = document.getElementById("inv-in-product");
    if (inProdSelect) {
      inProdSelect.value = prefillId;
      handleInProductChange();
    }
    sessionStorage.removeItem("cloudstock_prefill_product_id");
  }

   


  function switchSubTab(tab) {
    currentSubTab = tab;

    const btnTabIn = document.getElementById("tab-btn-inbound");
    const btnTabOut = document.getElementById("tab-btn-outbound");
    const panelIn = document.getElementById("panel-inbound");
    const panelOut = document.getElementById("panel-outbound");

    if (tab === "in") {
      if (btnTabIn) btnTabIn.classList.add("active");
      if (btnTabOut) btnTabOut.classList.remove("active");
      if (panelIn) panelIn.style.display = "block";
      if (panelOut) panelOut.style.display = "none";
    } else {
      if (btnTabIn) btnTabIn.classList.remove("active");
      if (btnTabOut) btnTabOut.classList.add("active");
      if (panelIn) panelIn.style.display = "none";
      if (panelOut) panelOut.style.display = "block";
    }
  }

   


  function handleInProductChange() {
    const select = document.getElementById("inv-in-product");
    const infoBox = document.getElementById("inv-in-prod-info");
    const currentQtyEl = document.getElementById("inv-in-current-qty");
    const minQtyEl = document.getElementById("inv-in-min-qty");
    const supSelect = document.getElementById("inv-in-supplier");

    const prodId = select?.value;
    const prod = productList.find((p) => p.productId === prodId);

    if (!prod) {
      if (infoBox) infoBox.style.display = "none";
      return;
    }

    if (currentQtyEl) currentQtyEl.textContent = formatNumber(prod.quantity);
    if (minQtyEl) minQtyEl.textContent = formatNumber(prod.minThreshold);
    if (infoBox) infoBox.style.display = "flex";

     
    if (supSelect && prod.supplierId) {
      supSelect.value = prod.supplierId;
    }
  }

  async function handleInboundSubmit(e) {
    e.preventDefault();

    const productId = document.getElementById("inv-in-product")?.value;
    const supplierId = document.getElementById("inv-in-supplier")?.value || null;
    const amountVal = document.getElementById("inv-in-amount")?.value;
    const note = document.getElementById("inv-in-note")?.value.trim();

    const amount = parseInt(amountVal, 10);

     
    if (!productId) {
      if (window.AuthModule) AuthModule.showToast("Vui long chon san pham can nhap kho", "warning");
      return;
    }

    if (isNaN(amount) || amount <= 0) {
      if (window.AuthModule) AuthModule.showToast("So luong nhap phai la so nguyen duong lon hon 0", "error");
      return;
    }

    const prod = productList.find((p) => p.productId === productId);
    if (!prod) return;

    const currentUser = ApiService.Auth.getCurrentUser();
    const performedBy = currentUser ? currentUser.fullName || currentUser.username : "Thủ kho";

     
    const invoiceUrl = attachedInvoiceName
      ? `s3://cloudstock-invoices-ap-southeast-1/invoices/${Date.now()}_${attachedInvoiceName}`
      : "";

    const transaction = {
      transactionId: "txn-" + Date.now().toString(36),
      timestamp: new Date().toISOString(),
      performedBy,
      type: "IN",
      productId,
      productName: prod.name,
      amount,
      supplierId,
      reason: note || "Nhap kho bo sung hang hoa",
      invoiceUrl,
    };

    try {
       
      await ApiService.Transactions.create(transaction);

       
      const supObj = supplierList.find((s) => s.supplierId === supplierId);
      const supName = supObj ? supObj.name : "Ngoai danh muc";
      const s3Log = attachedInvoiceName ? ` - File S3: ${attachedInvoiceName}` : "";

      MockDataStore.add("systemLogs", {
        timestamp: new Date().toISOString(),
        logStream: "lambda/inventoryService",
        level: "INFO",
        message: `POST /transactions [IN] - Nhap kho thanh cong: +${amount} ${prod.name} (NCC: ${supName}) boi ${performedBy}${s3Log}`,
      });

      if (window.AuthModule) {
        AuthModule.showToast(
          `Nhap kho thanh cong: +${amount} ${prod.name}. Ton kho moi: ${prod.quantity + amount}`,
          "success"
        );
      }

       
      document.getElementById("form-inbound")?.reset();
      document.getElementById("inv-in-prod-info").style.display = "none";
      attachedInvoiceName = "";
      attachedInvoiceData = "";
      const dropzoneText = document.getElementById("inv-dropzone-text");
      if (dropzoneText) {
        dropzoneText.textContent = "Keo tha hoa don / chung tu (PDF, JPG, PNG) hoac bam de chon tep";
      }

       
      await loadData();

       
      if (window.DashboardModule) DashboardModule.renderDashboard();
    } catch (err) {
      if (window.AuthModule) {
        AuthModule.showToast(`Loi nhap kho: ${err.message}`, "error");
      }
    }
  }

   


  function handleOutProductChange() {
    const select = document.getElementById("inv-out-product");
    const infoBox = document.getElementById("inv-out-prod-info");
    const currentQtyEl = document.getElementById("inv-out-current-qty");
    const minQtyEl = document.getElementById("inv-out-min-qty");

    const prodId = select?.value;
    const prod = productList.find((p) => p.productId === prodId);

    if (!prod) {
      if (infoBox) infoBox.style.display = "none";
      validateStockOut();
      return;
    }

    if (currentQtyEl) currentQtyEl.textContent = formatNumber(prod.quantity);
    if (minQtyEl) minQtyEl.textContent = formatNumber(prod.minThreshold);
    if (infoBox) infoBox.style.display = "flex";

    validateStockOut();
  }

  function validateStockOut() {
    const select = document.getElementById("inv-out-product");
    const amountInput = document.getElementById("inv-out-amount");
    const warningBox = document.getElementById("inv-out-warning-box");
    const submitBtn = document.getElementById("btn-submit-outbound");

    const prodId = select?.value;
    const prod = productList.find((p) => p.productId === prodId);
    const amount = parseInt(amountInput?.value, 10);

    if (!prod || isNaN(amount) || amount <= 0) {
      if (warningBox) warningBox.style.display = "none";
      if (submitBtn) submitBtn.disabled = false;
      return;
    }

    const currentQty = prod.quantity || 0;
    const minThreshold = prod.minThreshold || 0;
    const projectedQty = currentQty - amount;

     
    if (amount > currentQty) {
       
      if (warningBox) {
        warningBox.style.display = "block";
        warningBox.className = "login-error visible";
        warningBox.style.background = "var(--danger-light)";
        warningBox.style.borderColor = "#fecaca";
        warningBox.style.color = "var(--danger)";
        warningBox.textContent = `KHONG THE XUAT KHO! So luong xuat (${amount}) lon hon so luong ton kho hien tai (${currentQty}). Vui long kiem tra lai.`;
      }
      if (submitBtn) submitBtn.disabled = true;
    } else if (projectedQty < minThreshold) {
       
      if (warningBox) {
        warningBox.style.display = "block";
        warningBox.className = "login-error visible";
        warningBox.style.background = "var(--warning-light)";
        warningBox.style.borderColor = "#fde68a";
        warningBox.style.color = "var(--warning)";
        warningBox.textContent = `CANH BAO TON KHO THAP: Sau khi xuat, so luong ton con lai la ${projectedQty}, se thap hon muc toi thieu (${minThreshold}). He thong se tu dong ghi nhan canh bao CloudWatch & kich hoat Lambda SNS.`;
      }
      if (submitBtn) submitBtn.disabled = false;
    } else {
      if (warningBox) warningBox.style.display = "none";
      if (submitBtn) submitBtn.disabled = false;
    }
  }

  async function handleOutboundSubmit(e) {
    e.preventDefault();

    const productId = document.getElementById("inv-out-product")?.value;
    const amountVal = document.getElementById("inv-out-amount")?.value;
    const reasonSelect = document.getElementById("inv-out-reason-type")?.value;
    const note = document.getElementById("inv-out-note")?.value.trim();

    const amount = parseInt(amountVal, 10);

    if (!productId) {
      if (window.AuthModule) AuthModule.showToast("Vui long chon san pham can xuat kho", "warning");
      return;
    }

    if (isNaN(amount) || amount <= 0) {
      if (window.AuthModule) AuthModule.showToast("So luong xuat phai la so nguyen duong lon hon 0", "error");
      return;
    }

    const prod = productList.find((p) => p.productId === productId);
    if (!prod) return;

     
    if (amount > prod.quantity) {
      if (window.AuthModule) {
        AuthModule.showToast(
          `Loi chan xuat: So luong xuat (${amount}) vuot qua ton hien tai (${prod.quantity})`,
          "error"
        );
      }
      return;
    }

    const currentUser = ApiService.Auth.getCurrentUser();
    const performedBy = currentUser ? currentUser.fullName || currentUser.username : "Thủ kho";

     
    const fullReason = note ? `${reasonSelect} - ${note}` : reasonSelect;

    const transaction = {
      transactionId: "txn-" + Date.now().toString(36),
      timestamp: new Date().toISOString(),
      performedBy,
      type: "OUT",
      productId,
      productName: prod.name,
      amount,
      supplierId: null,
      reason: fullReason,
      invoiceUrl: "",
    };

    try {
       
      await ApiService.Transactions.create(transaction);

      const remainingQty = prod.quantity - amount;

       
      if (remainingQty < prod.minThreshold) {
         
        if (window.AuthModule) {
          AuthModule.showToast(
            `CANH BAO: Ton kho san pham ${prod.name} con ${remainingQty} (duoi nguong ${prod.minThreshold})! Da kich hoat Lambda SNS canh bao qua email.`,
            "warning"
          );
        }

         
        MockDataStore.add("systemLogs", {
          timestamp: new Date().toISOString(),
          logStream: "lambda/alertService",
          level: "WARN",
          message: `CANH BAO TON KHO: San pham ${prod.productId} (${prod.name}) giam xuong con ${remainingQty} < nguong toi thieu (${prod.minThreshold}). Lambda SNS: Da phat canh bao toi Ban quan ly kho.`,
        });
      } else {
        if (window.AuthModule) {
          AuthModule.showToast(
            `Xuat kho thanh cong: -${amount} ${prod.name}. Ton con lai: ${remainingQty}`,
            "success"
          );
        }
      }

       
      MockDataStore.add("systemLogs", {
        timestamp: new Date().toISOString(),
        logStream: "lambda/inventoryService",
        level: "INFO",
        message: `POST /transactions [OUT] - Xuat kho thanh cong: -${amount} ${prod.name} (Ly do: ${fullReason}) boi ${performedBy}`,
      });

       
      document.getElementById("form-outbound")?.reset();
      document.getElementById("inv-out-prod-info").style.display = "none";
      document.getElementById("inv-out-warning-box").style.display = "none";

       
      await loadData();

       
      if (window.DashboardModule) DashboardModule.renderDashboard();
    } catch (err) {
      if (window.AuthModule) {
        AuthModule.showToast(`Loi xuat kho: ${err.message}`, "error");
      }
    }
  }

   


  async function renderRecentTransactions() {
    const tbody = document.getElementById("inv-recent-table-body");
    if (!tbody) return;

    try {
      const res = await ApiService.Transactions.getAll();
      const allTxns = res.data || [];

       
      const recent = allTxns.slice(-5).reverse();

      if (recent.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="col-c text-muted cell-padded">Chua co giao dich nhap/xuat nao.</td></tr>`;
        return;
      }

      tbody.innerHTML = recent
        .map((t) => {
          const isIN = t.type === "IN";
          const typeBadge = isIN
            ? `<span class="badge badge-in">NHAP (+${formatNumber(t.amount)})</span>`
            : `<span class="badge badge-out">XUAT (-${formatNumber(t.amount)})</span>`;

          const invoiceIndicator = t.invoiceUrl
            ? `<span class="badge badge-info" title="${t.invoiceUrl}">Co chung tu S3</span>`
            : `<span class="text-muted">-</span>`;

          return `
            <tr>
              <td class="col-mono text-xs">${formatDateTime(t.timestamp)}</td>
              <td class="col-mono"><strong>${t.transactionId}</strong></td>
              <td>${typeBadge}</td>
              <td class="col-mono"><strong>${t.productId}</strong></td>
              <td>${t.productName}</td>
              <td>${t.reason || "-"}</td>
              <td><span class="text-muted">${t.performedBy || "-"}</span></td>
              <td class="col-c">${invoiceIndicator}</td>
            </tr>
          `;
        })
        .join("");
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="7" class="col-c text-danger">Loi tai lich su giao dich: ${err.message}</td></tr>`;
    }
  }

   


  function setupDropzone() {
    const dropzone = document.getElementById("inv-invoice-dropzone");
    const fileInput = document.getElementById("inv-invoice-file-input");
    const dropzoneText = document.getElementById("inv-dropzone-text");

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
        processInvoiceFile(e.dataTransfer.files[0]);
      }
    });

    fileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        processInvoiceFile(e.target.files[0]);
      }
    });

    function processInvoiceFile(file) {
       
      const validTypes = ["application/pdf", "image/jpeg", "image/png", "image/webp"];
      const isPdfOrImg = validTypes.includes(file.type) || file.name.match(/\.(pdf|jpe?g|png|webp)$/i);

      if (!isPdfOrImg) {
        if (window.AuthModule) {
          AuthModule.showToast("Chi chap nhan tep PDF, JPG hoac PNG", "warning");
        }
        return;
      }

      attachedInvoiceName = file.name;
      const reader = new FileReader();
      reader.onload = (evt) => {
        attachedInvoiceData = evt.target.result;
        if (dropzoneText) {
          dropzoneText.textContent = `Da chon tep: ${file.name} (${(file.size / 1024).toFixed(1)} KB) - San sang day len S3`;
        }
        if (window.AuthModule) {
          AuthModule.showToast(`Da nap chung tu ${file.name} vao phieu nhap (S3)`, "info");
        }
      };
      reader.readAsDataURL(file);
    }
  }

   


  function formatNumber(n) {
    if (typeof n !== "number" || isNaN(n)) return "0";
    return new Intl.NumberFormat("vi-VN").format(n);
  }

  function formatDateTime(iso) {
    if (!iso) return "-";
    try {
      const d = new Date(iso);
      const day = String(d.getDate()).padStart(2, "0");
      const month = String(d.getMonth() + 1).padStart(2, "0");
      const hours = String(d.getHours()).padStart(2, "0");
      const mins = String(d.getMinutes()).padStart(2, "0");
      return `${day}/${month} ${hours}:${mins}`;
    } catch {
      return iso;
    }
  }

   


  function init() {
     
    const inProd = document.getElementById("inv-in-product");
    if (inProd) inProd.addEventListener("change", handleInProductChange);

    const formIn = document.getElementById("form-inbound");
    if (formIn) formIn.addEventListener("submit", handleInboundSubmit);

     
    const outProd = document.getElementById("inv-out-product");
    if (outProd) outProd.addEventListener("change", handleOutProductChange);

    const outAmount = document.getElementById("inv-out-amount");
    if (outAmount) outAmount.addEventListener("input", validateStockOut);

    const formOut = document.getElementById("form-outbound");
    if (formOut) formOut.addEventListener("submit", handleOutboundSubmit);

     
    setupDropzone();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

   
  return {
    init,
    loadData,
    switchSubTab,
  };
})();
