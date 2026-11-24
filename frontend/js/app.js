window.debounce = function(func, delay = 300) {
  let timer;
  return function(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => func.apply(this, args), delay);
  };
};

const VIEW_TITLES = {
  dashboard: "Tổng quan (Dashboard)",
  products: "Quản lý Hàng hóa",
  suppliers: "Quản lý Nhà cung cấp",
  inventory: "Nghiệp vụ Kho (Nhập / Xuất)",
  reports: "Báo cáo & Tra cứu Hệ thống",
  profile: "Hồ sơ Cá nhân",
  users: "Quản lý Người dùng (Cognito Directory)",
};

const VIEW_DEFINITIONS = [
  { name: "dashboard", file: "views/dashboard.html" },
  { name: "products",  file: "views/products.html" },
  { name: "suppliers", file: "views/suppliers.html" },
  { name: "inventory", file: "views/inventory.html" },
  { name: "reports",   file: "views/reports.html" },
  { name: "profile",   file: "views/profile.html" },
  { name: "users",     file: "views/users.html" },
];

async function loadAllViews() {
  const mainContent = document.getElementById("main-content");
  if (!mainContent) return;

  try {
    const htmlSnippets = await Promise.all(
      VIEW_DEFINITIONS.map(async (v) => {
        const res = await fetch(`${v.file}?t=${Date.now()}`, { cache: "no-store" });
        if (!res.ok) {
          throw new Error(`Không thể nạp tệp: ${v.file} (HTTP ${res.status})`);
        }
        return await res.text();
      })
    );

    mainContent.innerHTML = htmlSnippets.join("\n");

    if (window.ProductsModule && typeof ProductsModule.init === "function") {
      ProductsModule.init();
    }
    if (window.SuppliersModule && typeof SuppliersModule.init === "function") {
      SuppliersModule.init();
    }
    if (window.InventoryModule && typeof InventoryModule.init === "function") {
      InventoryModule.init();
    }
    if (window.ReportsModule && typeof ReportsModule.init === "function") {
      ReportsModule.init();
    }
    if (window.AuthModule && typeof AuthModule.init === "function") {
      AuthModule.init();
    }

    switchView("dashboard");
  } catch (err) {
    console.error("Lỗi nạp view phân hệ:", err);
    mainContent.innerHTML = `
      <div class="card view-error-card">
        <div class="card-header">
          <h3 class="text-danger">Không thể nạp các file phân hệ (Views)</h3>
        </div>
        <div class="card-body view-error-body">
          <p>
            Các phân hệ HTML đã được phân tách thành các file độc lập trong thư mục <code>views/</code> phục vụ kiến trúc S3 Static Website Hosting.
          </p>
          <p class="text-muted text-sm">
            Chi tiết lỗi: <code>${err.message}</code>
          </p>
          <div class="notice-box">
            <strong>Lưu ý môi trường khởi chạy:</strong>
            <p>
              Khi mở trực tiếp tệp bằng trình duyệt qua giao thức <code>file:///</code>, chính sách bảo mật CORS sẽ chặn hàm <code>fetch()</code> nạp file cục bộ.
            </p>
            <p>
              <strong>Cách chạy ứng dụng:</strong>
            </p>
            <pre class="terminal-code-box">python3 -m http.server 8080</pre>
            <p>
              Sau đó truy cập: <a href="http://localhost:8080" target="_blank" class="link-primary-bold">http://localhost:8080</a> (hoặc lưu trữ trực tiếp trên AWS S3 Static Website Hosting).
            </p>
          </div>
        </div>
      </div>
    `;
  }
}

/**
 * Chuyển đổi màn hình hiển thị chính (Section Switcher)
 * @param {string} viewName - Tên định danh của view (dashboard, products, inventory...)
 */
function switchView(viewName) {
  const sections = document.querySelectorAll(".page-section");
  const navItems = document.querySelectorAll(".sidebar-nav .nav-item");
  const titleEl = document.getElementById("page-title");

  sections.forEach((sec) => sec.classList.remove("active"));
  navItems.forEach((item) => item.classList.remove("active"));

  const targetSec = document.getElementById(`view-${viewName}`);
  if (targetSec) {
    targetSec.classList.add("active");
  }

  const activeItem = document.querySelector(
    `.sidebar-nav .nav-item[data-view="${viewName}"]`
  );
  if (activeItem) {
    activeItem.classList.add("active");
  }

  if (titleEl && VIEW_TITLES[viewName]) {
    titleEl.textContent = VIEW_TITLES[viewName];
  }

  if (viewName === "dashboard" && window.DashboardModule) {
    DashboardModule.renderDashboard();
  } else if (viewName === "products" && window.ProductsModule) {
    ProductsModule.loadProducts();
  } else if (viewName === "suppliers" && window.SuppliersModule) {
    SuppliersModule.loadSuppliers();
  } else if (viewName === "inventory" && window.InventoryModule) {
    InventoryModule.loadData();
  } else if (viewName === "reports" && window.ReportsModule) {
    ReportsModule.loadData();
  } else if (viewName === "profile" && window.AuthModule) {
    AuthModule.renderProfile();
  } else if (viewName === "users" && window.AuthModule) {
    AuthModule.loadUserList();
  }
}

window.switchView = switchView;

/**
 * Khởi tạo tính năng Thu gọn / Mở rộng Sidebar
 * Hỗ trợ:
 * 1. Nút mũi tên trên sidebar (#sidebar-collapse-btn)
 * 2. Biểu tượng menu toggle trên header (#header-menu-toggle)
 * 3. Phím tắt Ctrl+B / Cmd+B hoặc Alt+S khi cần
 * 4. Tự động lưu trạng thái thu gọn vào localStorage
 * 5. Tự động đóng mobile drawer khi click overlay hoặc chọn phân hệ
 */
function initSidebar() {
  const collapseBtn = document.getElementById("sidebar-collapse-btn");
  const menuToggleBtn = document.getElementById("header-menu-toggle");
  const overlay = document.getElementById("sidebar-overlay");

  const isInitiallyCollapsed = localStorage.getItem("sidebar_collapsed") === "true";
  if (isInitiallyCollapsed) {
    document.body.classList.add("sidebar-collapsed");
    document.documentElement.classList.add("sidebar-collapsed");
    updateCollapseBtnState(true);
  }

  function updateCollapseBtnState(collapsed) {
    if (collapseBtn) {
      collapseBtn.title = collapsed
        ? "Mở rộng sidebar (Ctrl+B)"
        : "Thu gọn sidebar (Ctrl+B)";
      collapseBtn.setAttribute(
        "aria-label",
        collapsed ? "Mở rộng sidebar" : "Thu gọn sidebar"
      );
    }
  }

  function toggleSidebar() {
    const isMobile = window.innerWidth <= 768;
    if (isMobile) {
      document.body.classList.toggle("sidebar-mobile-open");
    } else {
      const isCollapsed = document.body.classList.toggle("sidebar-collapsed");
      document.documentElement.classList.toggle("sidebar-collapsed", isCollapsed);
      localStorage.setItem("sidebar_collapsed", isCollapsed ? "true" : "false");
      updateCollapseBtnState(isCollapsed);
    }
  }

  function closeMobileSidebar() {
    document.body.classList.remove("sidebar-mobile-open");
  }

  if (collapseBtn) {
    collapseBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleSidebar();
    });
  }

  if (menuToggleBtn) {
    menuToggleBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleSidebar();
    });
  }

  if (overlay) {
    overlay.addEventListener("click", closeMobileSidebar);
  }

  // Phím tắt bàn phím (Keyboard Shortcuts):
  // Ctrl + B / Cmd + B hoặc Alt + S
  window.addEventListener("keydown", (e) => {
    const isCtrlOrCmd = e.ctrlKey || e.metaKey;
    if (isCtrlOrCmd && (e.key === "b" || e.key === "B")) {
      e.preventDefault();
      toggleSidebar();
    } else if (e.altKey && (e.key === "s" || e.key === "S")) {
      e.preventDefault();
      toggleSidebar();
    } else if (e.key === "Escape" && document.body.classList.contains("sidebar-mobile-open")) {
      closeMobileSidebar();
    }
  });

  // Tự động đóng mobile sidebar khi chọn phân hệ
  document.querySelectorAll(".sidebar-nav .nav-item").forEach((item) => {
    item.addEventListener("click", () => {
      if (window.innerWidth <= 768) {
        closeMobileSidebar();
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initSidebar();

  document.querySelectorAll(".sidebar-nav .nav-item").forEach((item) => {
    item.addEventListener("click", () => {
      const view = item.getAttribute("data-view");
      const action = item.getAttribute("data-action");
      if (view) {
        switchView(view);
        if (action === "scroll-users") {
          setTimeout(() => {
            const el = document.getElementById("admin-user-mgmt");
            if (el) el.scrollIntoView({ behavior: "smooth" });
          }, 100);
        }
      }
    });
  });

  loadAllViews();
});
