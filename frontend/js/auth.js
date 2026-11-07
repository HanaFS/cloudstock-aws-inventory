const AuthModule = (() => {
   
  let allUsers = [];
  let filterKeyword = "";
  let filterRole = "ALL";
  let filterStatus = "ALL";

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

   


  function initLoginPage() {
    const form = document.getElementById("login-form");
    const errorBox = document.getElementById("login-error");
    const usernameInput = document.getElementById("login-username");
    const passwordInput = document.getElementById("login-password");
    const hintRows = document.querySelectorAll("#hint-accounts tr");

     
    if (ApiService.Auth.isAuthenticated()) {
      window.location.href = "index.html";
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
      const username = usernameInput.value.trim();
      const password = passwordInput.value;

      if (errorBox) {
        errorBox.textContent = "";
        errorBox.classList.remove("visible");
      }

      try {
        await ApiService.Auth.login(username, password);
        window.location.href = "index.html";
      } catch (err) {
        if (errorBox) {
          let msg = err.message || "Dang nhap that bai";
          if (msg.includes("LOCKED") || msg.includes("khoa")) {
            msg = "Tai khoan da bi khoa boi Quan tri vien";
          }
          errorBox.textContent = msg;
          errorBox.classList.add("visible");
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
        ApiService.Auth.logout();
        window.location.href = "login.html";
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
      console.error("Loi tai danh sach nguoi dung:", err);
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="7" class="col-c text-danger">Loi tai du lieu: ${err.message}</td></tr>`;
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
            Khong tim thay tai khoan nao phu hop voi bo loc.
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
      showToast("Chi Admin moi co quyen thay doi vai tro", "error");
      return;
    }
    try {
      const res = await ApiService.Users.getById(userId);
      const user = res.data;
      const newRole = user.role === "Admin" ? "Staff" : "Admin";
      await ApiService.Users.update(userId, { role: newRole });
      showToast(`Da doi vai tro cua ${user.username} thanh ${newRole}`, "success");
      loadUserList();
    } catch (err) {
      showToast(`Loi: ${err.message}`, "error");
    }
  }

  async function toggleUserStatus(userId) {
    const currentUser = ApiService.Auth.getCurrentUser();
    if (!currentUser || currentUser.role !== "Admin") {
      showToast("Chi Admin moi co quyen khoa/mo khoa tai khoan", "error");
      return;
    }
    try {
      const res = await ApiService.Users.getById(userId);
      const user = res.data;
      const newStatus = user.status === "ACTIVE" ? "LOCKED" : "ACTIVE";
      await ApiService.Users.update(userId, { status: newStatus });
      const actionText = newStatus === "LOCKED" ? "khoa" : "mo khoa";
      showToast(`Da ${actionText} tai khoan ${user.username}`, "success");
      loadUserList();
    } catch (err) {
      showToast(`Loi: ${err.message}`, "error");
    }
  }

  async function resetUserPassword(userId) {
    const user = allUsers.find((u) => u.id === userId);
    if (!user) return;

    showToast(
      `Amazon Cognito: Da gui lien ket khoi phuc mat khau den email ${user.email}`,
      "info"
    );

    MockDataStore.add("systemLogs", {
      timestamp: new Date().toISOString(),
      logStream: "lambda/authService",
      level: "INFO",
      message: `AdminResetUserPassword: Da phat yeu cau dat lai mat khau cho user '${user.username}' qua Cognito User Pool.`,
    });
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
    const currentUser = ApiService.Auth.getCurrentUser();
    if (!currentUser || currentUser.role !== "Admin") {
      showToast("Chi Admin moi co quyen tao tai khoan", "error");
      return;
    }

    const username = document.getElementById("new-user-username")?.value.trim();
    const fullName = document.getElementById("new-user-fullname")?.value.trim();
    const email = document.getElementById("new-user-email")?.value.trim();
    const role = document.getElementById("new-user-role")?.value;

    if (!username || !fullName || !email) {
      showToast("Vui long dien day du thong tin bat buoc", "warning");
      return;
    }

     
    const existing = allUsers.find((u) => u.username === username);
    if (existing) {
      showToast(`Ten dang nhap ${username} da ton tai trong he thong`, "error");
      return;
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

      MockDataStore.add("systemLogs", {
        timestamp: new Date().toISOString(),
        logStream: "lambda/authService",
        level: "INFO",
        message: `AdminCreateUser: Da tao thanh cong tai khoan moi '${username}' (Role: ${role}) tren Cognito User Pool.`,
      });

      showToast(`Tao tai khoan ${username} thanh cong (Cognito Simulated)`, "success");
      closeCreateUserModal();
      loadUserList();
    } catch (err) {
      showToast(`Loi tao tai khoan: ${err.message}`, "error");
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
    loadUserList,
    toggleUserRole,
    toggleUserStatus,
    resetUserPassword,
    openCreateUserModal,
    closeCreateUserModal,
    showToast,
  };
})();
