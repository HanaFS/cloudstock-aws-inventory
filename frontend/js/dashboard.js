const DashboardModule = (() => {
   
  let barChartInstance = null;
  let doughnutChartInstance = null;

   
  function formatCurrency(amount) {
    if (typeof amount !== "number" || isNaN(amount)) return "0 d";
    return new Intl.NumberFormat("vi-VN").format(amount) + " d";
  }

   
  function formatNumber(num) {
    if (typeof num !== "number" || isNaN(num)) return "0";
    return new Intl.NumberFormat("vi-VN").format(num);
  }

   
  function formatDateShort(isoString) {
    try {
      const d = new Date(isoString);
      const day = String(d.getDate()).padStart(2, "0");
      const month = String(d.getMonth() + 1).padStart(2, "0");
      return `${day}/${month}`;
    } catch {
      return isoString;
    }
  }

   


  function updateStatCards(products, transactions) {
     
    const totalProducts = products.length;

     
    const totalValue = products.reduce(
      (sum, p) => sum + (p.quantity || 0) * (p.price || 0),
      0
    );

     
    const today = new Date();
    const todayYear = today.getFullYear();
    const todayMonth = String(today.getMonth() + 1).padStart(2, "0");
    const todayDay = String(today.getDate()).padStart(2, "0");
    const todayPrefix = `${todayYear}-${todayMonth}-${todayDay}`;

    const todayTxns = transactions.filter((t) =>
      t.timestamp ? t.timestamp.startsWith(todayPrefix) : false
    );
    const todayIn = todayTxns
      .filter((t) => t.type === "IN")
      .reduce((sum, t) => sum + (t.amount || 0), 0);
    const todayOut = todayTxns
      .filter((t) => t.type === "OUT")
      .reduce((sum, t) => sum + (t.amount || 0), 0);

     
    const lowStockProducts = products.filter(
      (p) => (p.quantity || 0) < (p.minThreshold || 0)
    );

     
    const elTotalProducts = document.getElementById("stat-total-products");
    const elTotalValue = document.getElementById("stat-total-value");
    const elTodayTxns = document.getElementById("stat-today-txns");
    const elTodayBreakdown = document.getElementById("stat-today-breakdown");
    const elLowStock = document.getElementById("stat-low-stock");

    if (elTotalProducts) elTotalProducts.textContent = formatNumber(totalProducts);
    if (elTotalValue) elTotalValue.textContent = formatCurrency(totalValue);
    if (elTodayTxns) elTodayTxns.textContent = formatNumber(todayTxns.length);
    if (elTodayBreakdown) {
      elTodayBreakdown.textContent = `Nhap: +${formatNumber(todayIn)} | Xuat: -${formatNumber(todayOut)}`;
    }
    if (elLowStock) elLowStock.textContent = formatNumber(lowStockProducts.length);
  }

   


  function renderTransactionsBarChart(transactions) {
    const canvas = document.getElementById("chart-transactions-bar");
    if (!canvas || typeof Chart === "undefined") return;

     
    const days = [];
    const dateKeys = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const yyyy = d.getFullYear();
      const mm = String(d.getMonth() + 1).padStart(2, "0");
      const dd = String(d.getDate()).padStart(2, "0");
      const key = `${yyyy}-${mm}-${dd}`;
      dateKeys.push(key);
      days.push(`${dd}/${mm}`);
    }

     
    const inDataByDay = {};
    const outDataByDay = {};
    dateKeys.forEach((k) => {
      inDataByDay[k] = 0;
      outDataByDay[k] = 0;
    });

    transactions.forEach((t) => {
      if (!t.timestamp) return;
      const key = t.timestamp.slice(0, 10);
      if (key in inDataByDay) {
        if (t.type === "IN") {
          inDataByDay[key] += t.amount || 0;
        } else if (t.type === "OUT") {
          outDataByDay[key] += t.amount || 0;
        }
      }
    });

    const inSeries = dateKeys.map((k) => inDataByDay[k]);
    const outSeries = dateKeys.map((k) => outDataByDay[k]);

     
    if (barChartInstance) {
      barChartInstance.destroy();
      barChartInstance = null;
    }

    const ctx = canvas.getContext("2d");
    barChartInstance = new Chart(ctx, {
      type: "bar",
      data: {
        labels: days,
        datasets: [
          {
            label: "Nhap kho (IN)",
            data: inSeries,
            backgroundColor: "#2563eb",  
            borderColor: "#1d4ed8",
            borderWidth: 1,
            borderRadius: 4,
            barPercentage: 0.7,
            categoryPercentage: 0.6,
          },
          {
            label: "Xuat kho (OUT)",
            data: outSeries,
            backgroundColor: "#d97706",  
            borderColor: "#b45309",
            borderWidth: 1,
            borderRadius: 4,
            barPercentage: 0.7,
            categoryPercentage: 0.6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "top",
            align: "end",
            labels: {
              boxWidth: 12,
              boxHeight: 12,
              usePointStyle: false,
              font: {
                family: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif",
                size: 11,
              },
              color: "#64748b",
            },
          },
          tooltip: {
            backgroundColor: "#0f172a",
            titleFont: { size: 12, weight: "bold" },
            bodyFont: { size: 12 },
            padding: 10,
            cornerRadius: 6,
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              font: { size: 11 },
              color: "#94a3b8",
            },
          },
          y: {
            beginAtZero: true,
            grid: { color: "#f1f5f9" },
            ticks: {
              precision: 0,
              font: { size: 11 },
              color: "#94a3b8",
            },
          },
        },
      },
    });
  }

   


  function renderCategoryDoughnutChart(products) {
    const canvas = document.getElementById("chart-category-pie");
    if (!canvas || typeof Chart === "undefined") return;

     
    const categoryTotals = {};
    products.forEach((p) => {
      const cat = p.category || "Chua phan loai";
      categoryTotals[cat] = (categoryTotals[cat] || 0) + (p.quantity || 0);
    });

    const labels = Object.keys(categoryTotals);
    const data = Object.values(categoryTotals);

     
    const corporateColors = [
      "#0f172a",  
      "#2563eb",  
      "#0284c7",  
      "#0d9488",  
      "#64748b",  
      "#d97706",  
      "#7c3aed",  
    ];
    const backgroundColors = labels.map(
      (_, i) => corporateColors[i % corporateColors.length]
    );

     
    if (doughnutChartInstance) {
      doughnutChartInstance.destroy();
      doughnutChartInstance = null;
    }

    const ctx = canvas.getContext("2d");
    doughnutChartInstance = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: labels,
        datasets: [
          {
            data: data,
            backgroundColor: backgroundColors,
            borderColor: "#ffffff",
            borderWidth: 2,
            hoverOffset: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "68%",
        plugins: {
          legend: {
            position: "right",
            labels: {
              boxWidth: 10,
              boxHeight: 10,
              usePointStyle: false,
              font: {
                family: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif",
                size: 11,
              },
              color: "#64748b",
              padding: 12,
            },
          },
          tooltip: {
            backgroundColor: "#0f172a",
            titleFont: { size: 12, weight: "bold" },
            bodyFont: { size: 12 },
            padding: 10,
            cornerRadius: 6,
            callbacks: {
              label: function (context) {
                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                const val = context.raw || 0;
                const pct = total > 0 ? ((val / total) * 100).toFixed(1) : 0;
                return ` ${context.label}: ${formatNumber(val)} (${pct}%)`;
              },
            },
          },
        },
      },
    });
  }

   


  function renderLowStockTable(products) {
    const tbody = document.getElementById("low-stock-table-body");
    const badgeCount = document.getElementById("badge-low-stock-count");
    if (!tbody) return;

     
    const lowStockList = products.filter(
      (p) => (p.quantity || 0) < (p.minThreshold || 0)
    );

     
    lowStockList.sort((a, b) => {
      const deficitA = (a.minThreshold || 0) - (a.quantity || 0);
      const deficitB = (b.minThreshold || 0) - (b.quantity || 0);
      return deficitB - deficitA;
    });

    if (badgeCount) {
      badgeCount.textContent = `${lowStockList.length} mat hang`;
      badgeCount.className =
        lowStockList.length > 0 ? "badge badge-danger" : "badge badge-success";
    }

    if (lowStockList.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="col-c text-muted cell-padded">
            Moi mat hang trong kho deu dat tren nguong toi thieu an toan.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = lowStockList
      .map((p) => {
        const currentQty = p.quantity || 0;
        const minQty = p.minThreshold || 0;
        const deficit = minQty - currentQty;  

        return `
          <tr>
            <td class="col-mono">${p.productId}</td>
            <td><strong>${p.name}</strong></td>
            <td><span class="badge badge-neutral">${p.category}</span></td>
            <td class="col-r text-danger font-semibold">${formatNumber(currentQty)}</td>
            <td class="col-r text-muted">${formatNumber(minQty)}</td>
            <td class="col-r text-danger">+${formatNumber(deficit)}</td>
            <td class="col-c">
              <button
                type="button"
                class="btn btn-primary btn-sm"
                onclick="DashboardModule.quickStockIn('${p.productId}')"
                title="Tao phieu nhap kho cho ${p.name}"
              >
                Tao phieu nhap
              </button>
            </td>
          </tr>
        `;
      })
      .join("");
  }

   


  function quickStockIn(productId) {
     
    sessionStorage.setItem("cloudstock_prefill_product_id", productId);

     
    if (typeof window.switchView === "function") {
      window.switchView("inventory");
    }
    if (window.InventoryModule && typeof window.InventoryModule.switchSubTab === "function") {
      window.InventoryModule.switchSubTab("in");
    }

     
    if (window.AuthModule && typeof window.AuthModule.showToast === "function") {
      window.AuthModule.showToast(
        `Da chon ma san pham: ${productId} cho phieu nhap kho`,
        "info"
      );
    }
  }

   


  async function renderDashboard() {
    try {
       
      const [productsRes, txnsRes] = await Promise.all([
        ApiService.Products.getAll(),
        ApiService.Transactions.getAll(),
      ]);

      const products = productsRes.data || [];
      const transactions = txnsRes.data || [];

       
      updateStatCards(products, transactions);

       
      renderTransactionsBarChart(transactions);
      renderCategoryDoughnutChart(products);

       
      renderLowStockTable(products);
    } catch (err) {
      console.error("Loi khi render Dashboard:", err);
      if (window.AuthModule && typeof window.AuthModule.showToast === "function") {
        window.AuthModule.showToast("Loi tai du lieu Dashboard: " + err.message, "error");
      }
    }
  }

   
  return {
    renderDashboard,
    quickStockIn,
    formatCurrency,
    formatNumber,
  };
})();
