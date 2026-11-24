const AuthModule = (() => {
   
  let allUsers = [];
  let filterKeyword = "";
  let filterRole = "ALL";
  let filterStatus = "ALL";
  let isCreatingUser = false;

  function showToast(message, type = "info") {
    let container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.className = "toast-container";
      document.body.appendChild(container);
    }
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
      toast.classList.add("removing");
      setTimeout(() => toast.remove(), 200);
    }, 3000);
  }

   


  async function initLoginPage() {
    const form = document.getElementById("login-form");
    const errorBox = document.getElementById("login-error");
    const usernameInput = document.getElementById("login-username");
    const passwordInput = document.getElementById("login-password");
    const hintRows = document.querySelectorAll("#hint-accounts tr");
    const btnLogin = document.getElementById("btn-login");

    function showLoginError(message) {
      if (!errorBox) return;
      errorBox.textContent = message;
      errorBox.classList.add("visible");
    }

    try {
      const handledCallback = await ApiService.Auth.handleHostedUiCallback();
      if (handledCallback || ApiService.Auth.isAuthenticated()) {
        window.location.replace("index.html");
        return;
      }
    } catch (err) {
      showLoginError(err.message || "Đăng nhập Cognito thất bại.");
    }

    if (ApiService.Auth.isAuthenticated()) {
      window.location.replace("index.html");
      return;
    }

    hintRows.forEach((row) => {
      row.addEventListener("click", () => {
        const u = row.getAttribute("data-user");
        if (u && usernameInput) {
          usernameInput.value = u;
          if (passwordInput) passwordInput.value = "1";
          usernameInput.focus();
        }
      });
    });

    if (!form) return;

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const username = usernameInput ? usernameInput.value.trim() : "";
      const password = passwordInput ? passwordInput.value : "";

      if (errorBox) {
        errorBox.textContent = "";
        errorBox.classList.remove("visible");
      }

      if (btnLogin) {
        btnLogin.disabled = true;
        btnLogin.textContent = "Đang đăng nhập...";
      }

      try {
        await ApiService.Auth.login(username, password);
        window.location.href = "index.html";
      } catch (err) {
        let msg = err.message || "Đăng nhập thất bại";
        if (msg.includes("LOCKED") || msg.includes("khoa")) {
          msg = "Tài khoản đã bị khóa bởi Quản trị viên";
        }
        showLoginError(msg);
        if (btnLogin) {
          btnLogin.disabled = false;
          btnLogin.textContent = "Đăng nhập";
        }
      }
    });
  }

   


  function checkAuth() {
    const user = ApiService.Auth.getCurrentUser();
    if (!user) {
      window.location.href = "login.html";
      return null;
    }
    return user;
  }

  function renderUserHeaderAndSidebar(user) {
     
    const headerName = document.getElementById("header-user-name");
    const headerRole = document.getElementById("header-user-role");
    if (headerName) headerName.textContent = user.fullName || user.username;
    if (headerRole) {
      headerRole.textContent = user.role;
      headerRole.className = `header-role-badge role-${user.role.toLowerCase()}`;
    }

     
    const sbName = document.getElementById("sidebar-user-name");
    const sbRole = document.getElementById("sidebar-user-role");
    if (sbName) sbName.textContent = user.fullName || user.username;
    if (sbRole) sbRole.textContent = user.role;

     
    const adminNavItems = document.querySelectorAll(".admin-only");
    adminNavItems.forEach((el) => {
      if (user.role === "Admin") {
        el.classList.remove("hidden");
      } else {
        el.classList.add("hidden");
      }
    });
  }

  function setupLogout() {
    const logoutBtns = document.querySelectorAll(
      "#btn-logout, #sidebar-btn-logout"
    );
    logoutBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        try {
          const logoutUrl = ApiService.Auth.logout();
          window.location.href = logoutUrl || "login.html";
        } catch (err) {
          showToast(err.message || "Không thể đăng xuất.", "error");
        }
      });
    });
  }

   


  function renderProfile() {
    const user = ApiService.Auth.getCurrentUser();
    if (!user) return;

    const elId = document.getElementById("prof-id");
    const elUsername = document.getElementById("prof-username");
    const elFullName = document.getElementById("prof-fullname");
    const elEmail = document.getElementById("prof-email");
    const elRole = document.getElementById("prof-role");
    const elStatus = document.getElementById("prof-status");

    if (elId) elId.textContent = user.id;
    if (elUsername) elUsername.textContent = user.username;
    if (elFullName) elFullName.textContent = user.fullName;
    if (elEmail) elEmail.textContent = user.email;
    if (elRole) {
      elRole.textContent = user.role;
      elRole.className = `badge badge-${user.role.toLowerCase()}`;
    }
    if (elStatus) {
      elStatus.textContent = user.status;
      elStatus.className = `badge badge-${user.status.toLowerCase()}`;
    }
  }

  function openProfileEditModal() {
    const user = ApiService.Auth.getCurrentUser();
    if (!user) return;

    document.getElementById("edit-profile-fullname").value = user.fullName || "";
    document.getElementById("edit-profile-email").value = user.email || "";
    document.getElementById("modal-edit-profile")?.classList.add("visible");
  }

  function closeProfileEditModal() {
    document.getElementById("modal-edit-profile")?.classList.remove("visible");
  }

  async function handleProfileUpdate(e) {
    e.preventDefault();
    const user = ApiService.Auth.getCurrentUser();
    if (!user) {
      showToast("Phiên đăng nhập không hợp lệ. Vui lòng đăng nhập lại.", "error");
      return;
    }

    const fullName = document.getElementById("edit-profile-fullname").value.trim();
    const email = document.getElementById("edit-profile-email").value.trim();
    if (!fullName || fullName.length > 200 || !email || email.length > 320) {
      showToast("Vui lòng nhập họ tên và email hợp lệ.", "warning");
      return;
    }

    const submitButton = document.querySelector(
      "#form-edit-profile button[type='submit']"
    );
    if (submitButton?.disabled) return;
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "Đang lưu...";
    }

    try {
      const result = await ApiService.Users.update(user.id, { fullName, email });
      const savedUser = result.data || {};
      const updatedUser = {
        ...user,
        fullName: savedUser.fullName || fullName,
        email: savedUser.email || email,
      };
      localStorage.setItem("cloudstock_current_user", JSON.stringify(updatedUser));
      renderUserHeaderAndSidebar(updatedUser);
      renderProfile();
      closeProfileEditModal();
      showToast(
        CONFIG.USE_LOCAL_API_AUTH
          ? "Đã lưu hồ sơ trong chế độ local."
          : "Đã cập nhật thông tin hồ sơ.",
        "success"
      );
    } catch (err) {
      showToast(`Lỗi cập nhật hồ sơ: ${err.message}`, "error");
    } finally {
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = "Lưu thay đổi";
      }
    }
  }


  async function loadUserList() {
    const currentUser = ApiService.Auth.getCurrentUser();

     
    const accessDeniedBox = document.getElementById("user-access-denied");
    const userMainContent = document.getElementById("user-management-content");

    if (!currentUser || currentUser.role !== "Admin") {
      if (accessDeniedBox) accessDeniedBox.style.display = "block";
      if (userMainContent) userMainContent.style.display = "none";
      return;
    } else {
      if (accessDeniedBox) accessDeniedBox.style.display = "none";
      if (userMainContent) userMainContent.style.display = "block";
    }

    const tbody = document.getElementById("user-table-body");
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="7" class="col-c text-muted">Dang dong bo danh sach tai khoan tu Amazon Cognito...</td></tr>`;
    }

    try {
      const res = await ApiService.Users.getAll();
      allUsers = res.data || [];

      updateUserStats();
      renderUserTable();
    } catch (err) {
      console.error("Lỗi tải danh sách người dùng:", err);
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="7" class="col-c text-danger">Lỗi tải dữ liệu: ${err.message}</td></tr>`;
      }
    }
  }

  function updateUserStats() {
    const elTotal = document.getElementById("stat-user-total");
    const elAdmin = document.getElementById("stat-user-admin");
    const elStaff = document.getElementById("stat-user-staff");
    const elLocked = document.getElementById("stat-user-locked");

    const total = allUsers.length;
    const adminCount = allUsers.filter((u) => u.role === "Admin").length;
    const staffCount = allUsers.filter((u) => u.role === "Staff").length;
    const lockedCount = allUsers.filter((u) => u.status === "LOCKED").length;

    if (elTotal) elTotal.textContent = total;
    if (elAdmin) elAdmin.textContent = adminCount;
    if (elStaff) elStaff.textContent = staffCount;
    if (elLocked) elLocked.textContent = lockedCount;
  }

  function getFilteredUsers() {
    return allUsers.filter((u) => {
       
      const kw = filterKeyword.toLowerCase();
      const matchKeyword =
        !kw ||
        (u.username && u.username.toLowerCase().includes(kw)) ||
        (u.fullName && u.fullName.toLowerCase().includes(kw)) ||
        (u.email && u.email.toLowerCase().includes(kw));

       
      const matchRole = filterRole === "ALL" || u.role === filterRole;

       
      const matchStatus = filterStatus === "ALL" || u.status === filterStatus;

      return matchKeyword && matchRole && matchStatus;
    });
  }

  function renderUserTable() {
    const tbody = document.getElementById("user-table-body");
    const badgeCount = document.getElementById("user-total-badge");
    if (!tbody) return;

    const filtered = getFilteredUsers();

    if (badgeCount) {
      badgeCount.textContent = `${filtered.length} tai khoan`;
    }

    if (filtered.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="col-c text-muted cell-padded">
            Không tìm thấy tài khoản nào phù hợp với bộ lọc.
          </td>
        </tr>
      `;
      return;
    }

    const currentUser = ApiService.Auth.getCurrentUser();

    tbody.innerHTML = filtered
      .map((u) => {
        const isSelf = currentUser && currentUser.id === u.id;
        const statusBadge =
          u.status === "ACTIVE"
            ? `<span class="badge badge-active">ACTIVE</span>`
            : `<span class="badge badge-locked">LOCKED</span>`;
        const roleBadge =
          u.role === "Admin"
            ? `<span class="badge badge-admin">Admin</span>`
            : `<span class="badge badge-staff">Staff</span>`;

        const toggleRoleText = u.role === "Admin" ? "Ha xuong Staff" : "Nang len Admin";
        const toggleLockText = u.status === "ACTIVE" ? "Khoa" : "Mo khoa";
        const toggleLockClass = u.status === "ACTIVE" ? "btn-danger" : "btn-success";

        return `
          <tr>
            <td class="col-mono text-xs text-secondary">${u.id}</td>
            <td class="col-mono"><strong>${u.username}</strong></td>
            <td><strong>${u.fullName}</strong></td>
            <td class="col-mono">${u.email}</td>
            <td>${roleBadge}</td>
            <td>${statusBadge}</td>
            <td class="col-actions">
              ${
                isSelf
                  ? `<span class="text-muted text-xs">(Tai khoan cua ban)</span>`
                  : `
                    <button
                      type="button"
                      class="btn btn-secondary btn-sm"
                      onclick="AuthModule.toggleUserRole('${u.id}')"
                      title="Chuyen doi giua Admin va Staff"
                    >
                      ${toggleRoleText}
                    </button>
                    <button
                      type="button"
                      class="btn ${toggleLockClass} btn-sm"
                      onclick="AuthModule.toggleUserStatus('${u.id}')"
                      title="Khoa hoac Mo khoa tai khoan nay"
                    >
                      ${toggleLockText}
                    </button>
                    <button
                      type="button"
                      class="btn btn-ghost btn-sm"
                      onclick="AuthModule.resetUserPassword('${u.id}')"
                      title="Gui email dat lai mat khau qua Cognito"
                    >
                      Reset Mat khau
                    </button>
                  `
              }
            </td>
          </tr>
        `;
      })
      .join("");
  }

  async function toggleUserRole(userId) {
    const currentUser = ApiService.Auth.getCurrentUser();
    if (!currentUser || currentUser.role !== "Admin") {
      showToast("Chỉ Admin mới có quyền thay đổi vai trò", "error");
      return;
    }
    try {
      const res = await ApiService.Users.getById(userId);
      const user = res.data;
      const newRole = user.role === "Admin" ? "Staff" : "Admin";
      await ApiService.Users.update(userId, { role: newRole });
      showToast(`Đã đổi vai trò của ${user.username} thành ${newRole}`, "success");
      loadUserList();
    } catch (err) {
      showToast(`Lỗi: ${err.message}`, "error");
    }
  }

  async function toggleUserStatus(userId) {
    const currentUser = ApiService.Auth.getCurrentUser();
    if (!currentUser || currentUser.role !== "Admin") {
      showToast("Chỉ Admin mới có quyền khoá/mở khoá tài khoản", "error");
      return;
    }
    try {
      const res = await ApiService.Users.getById(userId);
      const user = res.data;
      const newStatus = user.status === "ACTIVE" ? "LOCKED" : "ACTIVE";
      await ApiService.Users.update(userId, { status: newStatus });
      const actionText = newStatus === "LOCKED" ? "khoá" : "mở khoá";
      showToast(`Đã ${actionText} tài khoản ${user.username}`, "success");
      loadUserList();
    } catch (err) {
      showToast(`Lỗi: ${err.message}`, "error");
    }
  }

  async function resetUserPassword(userId) {
    const user = allUsers.find((u) => u.id === userId);
    if (!user) return;

    try {
      await ApiService.Users.resetPassword(userId);
      showToast(
        CONFIG.USE_LOCAL_API_AUTH
          ? `Đã mô phỏng đặt lại mật khẩu cho ${user.username} trong chế độ local`
          : `Đã gửi yêu cầu đặt lại mật khẩu đến email ${user.email}`,
        "success"
      );
    } catch (err) {
      showToast(`Lỗi đặt lại mật khẩu: ${err.message}`, "error");
    }
  }

  function openCreateUserModal() {
    const modal = document.getElementById("modal-create-user");
    if (modal) {
      document.getElementById("form-create-user")?.reset();
      modal.classList.add("visible");
    }
  }

  function closeCreateUserModal() {
    const modal = document.getElementById("modal-create-user");
    if (modal) modal.classList.remove("visible");
  }

  async function handleCreateUser(e) {
    e.preventDefault();
    if (isCreatingUser) return;

    const currentUser = ApiService.Auth.getCurrentUser();
    if (!currentUser || currentUser.role !== "Admin") {
      showToast("Chỉ Admin mới có quyền tạo tài khoản", "error");
      return;
    }

    const username = document.getElementById("new-user-username")?.value.trim();
    const fullName = document.getElementById("new-user-fullname")?.value.trim();
    const email = document.getElementById("new-user-email")?.value.trim();
    const role = document.getElementById("new-user-role")?.value;

    if (!username || !fullName || !email) {
      showToast("Vui lòng điền đầy đủ thông tin bắt buộc", "warning");
      return;
    }

     
    const existing = allUsers.find((u) => u.username === username);
    if (existing) {
      showToast(`Tên đăng nhập ${username} đã tồn tại trong hệ thống`, "error");
      return;
    }

    isCreatingUser = true;
    const submitButton = document.querySelector(
      "#form-create-user button[type='submit']"
    );
    const originalButtonText = submitButton ? submitButton.textContent : "";
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "Đang tạo...";
    }

    try {
      const newUser = {
        id: "u-" + Date.now().toString(36),
        username,
        fullName,
        email,
        role: role || "Staff",
        status: "ACTIVE",
      };

      await ApiService.Users.create(newUser);

      if (typeof MockDataStore !== "undefined") {
        MockDataStore.add("systemLogs", {
          timestamp: new Date().toISOString(),
          logStream: "lambda/authService",
          level: "INFO",
          message: `AdminCreateUser: Đã tạo thành công tài khoản mới '${username}' (Role: ${role}) trên Cognito User Pool.`,
        });
      }

      showToast(
        CONFIG.USE_LOCAL_API_AUTH
          ? `Đã thêm ${username} vào danh sách local (không tạo tài khoản Cognito)`
          : `Tạo tài khoản ${username} thành công`,
        "success"
      );
      closeCreateUserModal();
      loadUserList();
    } catch (err) {
      showToast(`Lỗi tạo tài khoản: ${err.message}`, "error");
    } finally {
      isCreatingUser = false;
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = originalButtonText;
      }
    }
  }

  function setupUserFilters() {
    const searchInput = document.getElementById("user-search-input");
    const roleSelect = document.getElementById("user-filter-role");
    const statusSelect = document.getElementById("user-filter-status");
    const resetBtn = document.getElementById("btn-reset-user-filter");

    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        filterKeyword = e.target.value.trim();
        renderUserTable();
      });
    }

    if (roleSelect) {
      roleSelect.addEventListener("change", (e) => {
        filterRole = e.target.value;
        renderUserTable();
      });
    }

    if (statusSelect) {
      statusSelect.addEventListener("change", (e) => {
        filterStatus = e.target.value;
        renderUserTable();
      });
    }

    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        filterKeyword = "";
        filterRole = "ALL";
        filterStatus = "ALL";
        if (searchInput) searchInput.value = "";
        if (roleSelect) roleSelect.value = "ALL";
        if (statusSelect) statusSelect.value = "ALL";
        renderUserTable();
      });
    }
  }

   


  function init() {
    const isLogin = window.location.pathname.endsWith("login.html");
    if (isLogin) {
      initLoginPage();
    } else {
      const user = checkAuth();
      if (!user) return;
      renderUserHeaderAndSidebar(user);
      setupLogout();
      setupUserFilters();

       
      const formCreate = document.getElementById("form-create-user");
      if (formCreate) formCreate.addEventListener("submit", handleCreateUser);

      const formProfile = document.getElementById("form-edit-profile");
      if (formProfile && formProfile.dataset.submitBound !== "true") {
        formProfile.addEventListener("submit", handleProfileUpdate);
        formProfile.dataset.submitBound = "true";
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

   
  return {
    init,
    checkAuth,
    renderProfile,
    openProfileEditModal,
    closeProfileEditModal,
    loadUserList,
    toggleUserRole,
    toggleUserStatus,
    resetUserPassword,
    openCreateUserModal,
    closeCreateUserModal,
    showToast,
  };
})();
window.AuthModule = AuthModule