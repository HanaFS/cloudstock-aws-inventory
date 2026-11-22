const ReportsModule = (() => {
   
  let transactionList = [];
  let filterTxnKeyword = "";
  let filterTxnType = "ALL";
  let filterTxnPerformer = "ALL";

   
  let logList = [];
  let filterLogLevel = "ALL";
  let filterLogKeyword = "";

   
  async function loadData() {
    await Promise.all([loadTransactions(), loadLogs()]);
  }

   

  async function loadTransactions() {
    const tbody = document.getElementById("report-txn-table-body");
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="9" class="col-c text-muted">Đang truy vấn dữ liệu DynamoDB...</td></tr>`;
    }

    try {
      const [txnRes, supRes] = await Promise.all([
        ApiService.Transactions.getAll(),
        ApiService.Suppliers.getAll(),
      ]);

      const rawTxns = txnRes.data || [];
      const suppliers = supRes.data || [];

       
      const supMap = {};
      suppliers.forEach((s) => {
        supMap[s.supplierId] = s.name;
      });

      transactionList = rawTxns
        .map((t) => ({
          ...t,
          supplierName: t.supplierId ? supMap[t.supplierId] || t.supplierId : "",
        }))
        .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

      populatePerformerFilter();
      renderTransactionsTable();
    } catch (err) {
      console.error("Lỗi tải lịch sử giao dịch:", err);
      if (window.AuthModule) {
        AuthModule.showToast("Lỗi tải giao dịch: " + err.message, "error");
      }
    }
  }

  function populatePerformerFilter() {
    const select = document.getElementById("report-filter-performer");
    if (!select) return;

    const performers = Array.from(
      new Set(transactionList.map((t) => t.performedBy).filter(Boolean))
    );

    let html = `<option value="ALL">Tất cả người thực hiện</option>`;
    performers.forEach((p) => {
      html += `<option value="${p}">${p}</option>`;
    });
    select.innerHTML = html;
  }

  function getFilteredTransactions() {
    return transactionList.filter((t) => {
       
      const kw = filterTxnKeyword.toLowerCase();
      const matchKeyword =
        !kw ||
        (t.productId && t.productId.toLowerCase().includes(kw)) ||
        (t.productName && t.productName.toLowerCase().includes(kw)) ||
        (t.transactionId && t.transactionId.toLowerCase().includes(kw));

       
      const matchType = filterTxnType === "ALL" || t.type === filterTxnType;

       
      const matchPerformer =
        filterTxnPerformer === "ALL" || t.performedBy === filterTxnPerformer;

      return matchKeyword && matchType && matchPerformer;
    });
  }

  function renderTransactionsTable() {
    const tbody = document.getElementById("report-txn-table-body");
    const badgeCount = document.getElementById("report-txn-count-badge");
    if (!tbody) return;

    const filtered = getFilteredTransactions();

    if (badgeCount) {
      badgeCount.textContent = `${filtered.length} giao dich`;
    }

    if (filtered.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" class="col-c text-muted cell-padded">
            Không tìm thấy giao dịch nào phù hợp với tiêu chí tra cứu.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = filtered
      .map((t) => {
        const isIN = t.type === "IN";
        const typeBadge = isIN
          ? `<span class="badge badge-in">NHẬP KHO</span>`
          : `<span class="badge badge-out">XUẤT KHO</span>`;

        const amountFormatted = isIN
          ? `<span class="text-success font-semibold">+${formatNumber(t.amount)}</span>`
          : `<span class="text-danger font-semibold">-${formatNumber(t.amount)}</span>`;

        let reasonOrSupplier = t.reason || "-";
        if (isIN && t.supplierName) {
          reasonOrSupplier = `NCC: ${t.supplierName}${t.reason ? `(${t.reason})` : ""}`;
        }

        const invoiceLink = t.invoiceUrl
          ? `<a href="javascript:void(0)" class="badge badge-info" onclick="ReportsModule.viewInvoice('${t.transactionId}')" title="${t.invoiceUrl}">Xem chứng từ S3</a>`
          : `<span class="text-muted">-</span>`;

        return `
          <tr>
            <td class="col-mono"><strong>${t.transactionId}</strong></td>
            <td class="col-mono text-xs">${formatDateTime(t.timestamp)}</td>
            <td><span class="text-muted">${t.performedBy || "-"}</span></td>
            <td>${typeBadge}</td>
            <td class="col-mono"><strong>${t.productId}</strong></td>
            <td><strong>${t.productName}</strong></td>
            <td class="col-r">${amountFormatted}</td>
            <td class="cell-wrap-text">${reasonOrSupplier}</td>
            <td class="col-c">${invoiceLink}</td>
          </tr>
        `;
      })
      .join("");
  }

  function viewInvoice(transactionId) {
    const t = transactionList.find((item) => item.transactionId === transactionId);
    if (!t || !t.invoiceUrl) return;

    if (window.AuthModule) {
      AuthModule.showToast(
        `Pre-signed URL S3: ${t.invoiceUrl} (Giao dịch: ${t.transactionId})`,
        "info"
      );
    }
  }

  function exportExcel() {
    const filtered = getFilteredTransactions();
    if (filtered.length === 0) {
      if (window.AuthModule) AuthModule.showToast("Không có dữ liệu để xuất Excel", "warning");
      return;
    }

    if (typeof XLSX === "undefined") {
      if (window.AuthModule) AuthModule.showToast("Thu vien SheetJS chua duoc nap", "error");
      return;
    }

    const rows = filtered.map((t, idx) => ({
      STT: idx + 1,
      "Ma Giao Dich": t.transactionId,
      "Ngay Gio": formatDateTimeFull(t.timestamp),
      "Nguoi Thuc Hien": t.performedBy || "",
      "Loại Thao Tác": t.type === "IN" ? "Nhập kho" : "Xuất kho",
      "Ma San Pham": t.productId,
      "Ten San Pham": t.productName,
      "So Luong": t.amount,
      "Lý Do / Nhà Cung Cấp": t.supplierName ? `NCC: ${t.supplierName} (${t.reason || ""})` : t.reason || "",
      "Chứng Từ S3": t.invoiceUrl || "Không có",
    }));

    const ws = XLSX.utils.json_to_sheet(rows);
    ws["!cols"] = [
      { wch: 6 },
      { wch: 15 },
      { wch: 20 },
      { wch: 18 },
      { wch: 14 },
      { wch: 12 },
      { wch: 28 },
      { wch: 10 },
      { wch: 32 },
      { wch: 35 },
    ];

    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "LichSuGiaoDich");

    const dateStr = new Date().toISOString().slice(0, 10);
    const fileName = `CloudStock_Transactions_${dateStr}.xlsx`;
    XLSX.writeFile(wb, fileName);

    if (window.AuthModule) {
      AuthModule.showToast(`Đã xuất file Excel: ${fileName}`, "success");
    }
  }

  function exportPDF() {
    const filtered = getFilteredTransactions();
    if (filtered.length === 0) {
      if (window.AuthModule) AuthModule.showToast("Không có dữ liệu để xuất PDF", "warning");
      return;
    }

    if (typeof html2pdf === "undefined") {
      if (window.AuthModule) AuthModule.showToast("Thu vien html2pdf chua duoc nap", "error");
      return;
    }

    const currentUser = ApiService.Auth.getCurrentUser();
    const performer = currentUser ? currentUser.fullName || currentUser.username : "Thủ kho";
    const now = new Date();
    const nowStr = `${now.toLocaleDateString("vi-VN")} ${now.toLocaleTimeString("vi-VN")}`;

    const totalIn = filtered
      .filter((t) => t.type === "IN")
      .reduce((sum, t) => sum + (t.amount || 0), 0);
    const totalOut = filtered
      .filter((t) => t.type === "OUT")
      .reduce((sum, t) => sum + (t.amount || 0), 0);

    const printContainer = document.createElement("div");
    printContainer.className = "pdf-report-container";

    printContainer.innerHTML = `
      <div class="pdf-report-header">
        <div>
          <h1 class="pdf-report-title">CloudStock Serverless Inventory</h1>
          <p class="pdf-report-subtitle">Bao cao Lich su Giao dich Nhap / Xuat Kho</p>
        </div>
        <div class="pdf-report-meta">
          <div>Ngay lap: <strong>${nowStr}</strong></div>
          <div>Nguoi lap: <strong>${performer}</strong></div>
        </div>
      </div>

      <div class="pdf-summary-grid">
        <div class="pdf-summary-card">
          <div class="pdf-summary-label">Tong so giao dich</div>
          <div class="pdf-summary-value">${filtered.length}</div>
        </div>
        <div class="pdf-summary-card pdf-summary-in">
          <div class="pdf-summary-label pdf-summary-label-in">Tong nhap (IN)</div>
          <div class="pdf-summary-value pdf-summary-value-in">+${formatNumber(totalIn)}</div>
        </div>
        <div class="pdf-summary-card pdf-summary-out">
          <div class="pdf-summary-label pdf-summary-label-out">Tong xuat (OUT)</div>
          <div class="pdf-summary-value pdf-summary-value-out">-${formatNumber(totalOut)}</div>
        </div>
      </div>

      <table class="pdf-table">
        <thead>
          <tr class="pdf-thead-tr">
            <th class="pdf-th">Mã GD</th>
            <th class="pdf-th">Thời gian</th>
            <th class="pdf-th">Người TH</th>
            <th class="pdf-th-c">Loại</th>
            <th class="pdf-th">Mã SP</th>
            <th class="pdf-th">Tên mặt hàng</th>
            <th class="pdf-th-r">Số lượng</th>
            <th class="pdf-th">Lý do / NCC</th>
          </tr>
        </thead>
        <tbody>
          ${filtered
            .slice(0, 35)
            .map(
              (t) => `
            <tr class="pdf-tr">
              <td class="pdf-td col-mono"><strong>${t.transactionId}</strong></td>
              <td class="pdf-td col-mono">${formatDateTime(t.timestamp)}</td>
              <td class="pdf-td">${t.performedBy || "-"}</td>
              <td class="pdf-td-c font-semibold ${t.type === "IN" ? "text-success" : "text-danger"}">
                ${t.type === "IN" ? "NHẬP" : "XUẤT"}
              </td>
              <td class="pdf-td col-mono">${t.productId}</td>
              <td class="pdf-td">${t.productName}</td>
              <td class="pdf-td-r font-semibold">
                ${t.type === "IN" ? "+" : "-"}${formatNumber(t.amount)}
              </td>
              <td class="pdf-td text-secondary">${t.supplierName ? `NCC: ${t.supplierName}` : t.reason || "-"}</td>
            </tr>
          `
            )
            .join("")
          }
        </tbody>
      </table>

      ${
        filtered.length > 35
          ? `<p class="pdf-notice">(Hiển thị 35 trên tổng số ${filtered.length} bản ghi trong file in PDF)</p>`
          : ""
      }

      <div class="pdf-sign-row">
        <div class="pdf-sign-box">
          <p class="pdf-sign-title">Người lập biểu</p>
          <div class="pdf-sign-name">${performer}</div>
        </div>
        <div class="pdf-sign-box">
          <p class="pdf-sign-title">Xác nhận Quản lý</p>
          <div class="pdf-sign-name">Ban Giam Doc</div>
        </div>
      </div>
    `;

    const opt = {
      margin: 10,
      filename: `CloudStock_Transactions_${now.toISOString().slice(0, 10)}.pdf`,
      image: { type: "jpeg", quality: 0.98 },
      html2canvas: { scale: 2 },
      jsPDF: { unit: "mm", format: "a4", orientation: "landscape" },
    };

    html2pdf()
      .set(opt)
      .from(printContainer)
      .save()
      .then(() => {
        if (window.AuthModule) AuthModule.showToast("Đã xuất báo cáo PDF thành công", "success");
      })
      .catch((err) => {
        if (window.AuthModule) AuthModule.showToast("Lỗi xuất PDF: " + err.message, "error");
      });
  }

   


  async function loadLogs() {
    const tbody = document.getElementById("report-log-table-body");
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="4" class="col-c text-muted">Đang kết nối Amazon CloudWatch Logs API...</td></tr>`;
    }

    try {
      const res = await ApiService.SystemLogs.getAll();
      logList = (res.data || []).sort(
        (a, b) => new Date(b.timestamp) - new Date(a.timestamp)
      );

      updateLogCounterBadges();
      renderLogsTable();
    } catch (err) {
      console.error("Lỗi tải CloudWatch logs:", err);
      if (window.AuthModule) {
        AuthModule.showToast("Lỗi tải CloudWatch Logs: " + err.message, "error");
      }
    }
  }

  function updateLogCounterBadges() {
    const badgeAll = document.getElementById("log-count-all");
    const badgeInfo = document.getElementById("log-count-info");
    const badgeWarn = document.getElementById("log-count-warn");
    const badgeError = document.getElementById("log-count-error");

    if (badgeAll) badgeAll.textContent = logList.length;
    if (badgeInfo) badgeInfo.textContent = logList.filter((l) => l.level === "INFO").length;
    if (badgeWarn) badgeWarn.textContent = logList.filter((l) => l.level === "WARN").length;
    if (badgeError) badgeError.textContent = logList.filter((l) => l.level === "ERROR").length;
  }

  function getFilteredLogs() {
    return logList.filter((l) => {
      const kw = filterLogKeyword.toLowerCase();
      const matchKeyword =
        !kw ||
        (l.message && l.message.toLowerCase().includes(kw)) ||
        (l.logStream && l.logStream.toLowerCase().includes(kw));

      const matchLevel = filterLogLevel === "ALL" || l.level === filterLogLevel;

      return matchKeyword && matchLevel;
    });
  }

  function renderLogsTable() {
    const tbody = document.getElementById("report-log-table-body");
    if (!tbody) return;

    const filtered = getFilteredLogs();

    if (filtered.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="4" class="col-c text-muted cell-padded">
            Không tìm thấy bản ghi log nào phù hợp với bộ lọc.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = filtered
      .map((l) => {
        let levelBadge = "";
        let rowClass = "cloudwatch-row-info";

        if (l.level === "ERROR") {
          levelBadge = `<span class="badge badge-log-error">ERROR</span>`;
          rowClass = "cloudwatch-row-error";
        } else if (l.level === "WARN") {
          levelBadge = `<span class="badge badge-log-warn">WARN</span>`;
          rowClass = "cloudwatch-row-warn";
        } else {
          levelBadge = `<span class="badge badge-log-info">INFO</span>`;
          rowClass = "cloudwatch-row-info";
        }

        return `
          <tr class="${rowClass}">
            <td class="col-mono text-xs cloudwatch-cell-time">
              ${l.timestamp}
            </td>
            <td class="col-mono text-xs cloudwatch-cell-stream">
              ${l.logStream || "system"}
            </td>
            <td class="col-c">${levelBadge}</td>
            <td class="col-mono text-sm cloudwatch-cell-msg">
              ${escapeHtml(l.message || "")}
            </td>
          </tr>
        `;
      })
      .join("");
  }

   


  function simulateCloudWatchEvent() {
     
    const eventTypes = [
      {
        stream: "/aws/lambda/s3UploadPresignedUrl",
        level: "INFO",
        msg: `S3 Event: s3:ObjectCreated:Put vao bucket 'cloudstock-invoices-ap-southeast-1' - Key: 'invoices/${Date.now()}_chungtu_demo.pdf' (size: 245KB) - Pre-signed URL verified.`,
      },
      {
        stream: "/aws/lambda/processStockTransaction",
        level: "WARN",
        msg: `SNS Publish: Topic 'arn:aws:sns:ap-southeast-1:123456789:InventoryLowStockAlert' được kích hoạt bởi DynamoDB Streams. Sản phẩm prod-002 xuống dưới ngưỡng an toàn (8 < 50). Email đã gửi tới Ban Quản Lý.`,
      },
      {
        stream: "/aws/lambda/inventoryService",
        level: "ERROR",
        msg: `DynamoDB ConditionalCheckFailedException: Giao dịch xuất kho prod-007 bị từ chối do tồn kho hiện tại nhỏ hơn số lượng yêu cầu (Requested: 50, Available: 3). HTTP 400 Bad Request.`,
      },
    ];

     
    const ev = eventTypes[Math.floor(Math.random() * eventTypes.length)];

    if (typeof MockDataStore !== "undefined") {
      MockDataStore.add("systemLogs", {
        timestamp: new Date().toISOString(),
        logStream: ev.stream,
        level: ev.level,
        message: ev.msg,
      });
    }

    loadLogs();

    if (window.AuthModule) {
      AuthModule.showToast(
        `Đã bắn sự kiện CloudWatch mới: [${ev.level}] ${ev.stream}`,
        ev.level === "ERROR" ? "error" : ev.level === "WARN" ? "warning" : "info"
      );
    }
  }

   


  function setupFilters() {
     
    const searchTxn = document.getElementById("report-search-txn");
    const typeTxn = document.getElementById("report-filter-type");
    const performerTxn = document.getElementById("report-filter-performer");
    const resetTxn = document.getElementById("btn-reset-report-txn");

    if (searchTxn) {
      searchTxn.addEventListener("input", (e) => {
        filterTxnKeyword = e.target.value.trim();
        renderTransactionsTable();
      });
    }

    if (typeTxn) {
      typeTxn.addEventListener("change", (e) => {
        filterTxnType = e.target.value;
        renderTransactionsTable();
      });
    }

    if (performerTxn) {
      performerTxn.addEventListener("change", (e) => {
        filterTxnPerformer = e.target.value;
        renderTransactionsTable();
      });
    }

    if (resetTxn) {
      resetTxn.addEventListener("click", () => {
        filterTxnKeyword = "";
        filterTxnType = "ALL";
        filterTxnPerformer = "ALL";
        if (searchTxn) searchTxn.value = "";
        if (typeTxn) typeTxn.value = "ALL";
        if (performerTxn) performerTxn.value = "ALL";
        renderTransactionsTable();
      });
    }

     
    const searchLog = document.getElementById("report-search-log");
    const levelLog = document.getElementById("report-filter-log-level");
    const refreshLogBtn = document.getElementById("btn-refresh-cloudwatch-logs");
    const simulateLogBtn = document.getElementById("btn-simulate-cloudwatch-event");

    if (searchLog) {
      searchLog.addEventListener("input", (e) => {
        filterLogKeyword = e.target.value.trim();
        renderLogsTable();
      });
    }

    if (levelLog) {
      levelLog.addEventListener("change", (e) => {
        filterLogLevel = e.target.value;
        renderLogsTable();
      });
    }

    if (refreshLogBtn) {
      refreshLogBtn.addEventListener("click", () => {
        loadLogs();
        if (window.AuthModule) {
          AuthModule.showToast("Đã đồng bộ toàn bộ Log Streams từ CloudWatch", "info");
        }
      });
    }

    if (simulateLogBtn) {
      simulateLogBtn.addEventListener("click", simulateCloudWatchEvent);
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

  function formatDateTimeFull(iso) {
    if (!iso) return "-";
    try {
      const d = new Date(iso);
      return d.toLocaleString("vi-VN");
    } catch {
      return iso;
    }
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

   


  function init() {
    setupFilters();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

   
  return {
    init,
    loadData,
    loadTransactions,
    loadLogs,
    viewInvoice,
    exportExcel,
    exportPDF,
    simulateCloudWatchEvent,
  };
})();
window.ReportsModule = ReportsModule