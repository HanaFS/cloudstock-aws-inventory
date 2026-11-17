const ApiService = (() => {
  const LOCAL_API_RESOURCES = new Set(["products", "suppliers", "transactions"]);

  function _delay(ms = CONFIG.MOCK_DELAY_MS) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function _usesMockData(resource) {
    return (
      CONFIG.USE_MOCK_DATA &&
      !(CONFIG.USE_LOCAL_API && LOCAL_API_RESOURCES.has(resource))
    );
  }

  function _getToken() {
    if (CONFIG.USE_LOCAL_API_AUTH) {
      if (!CONFIG.USE_LOCAL_API || !CONFIG.USE_MOCK_AUTH) {
        throw new Error("Xác thực local chỉ dùng cùng API local và tài khoản mock.");
      }

      let apiUrl;
      try {
        apiUrl = new URL(CONFIG.API_BASE_URL);
      } catch {
        throw new Error("API_BASE_URL không hợp lệ cho xác thực local.");
      }
      if (!["localhost", "127.0.0.1"].includes(apiUrl.hostname)) {
        throw new Error("Xác thực local chỉ được gửi tới API trên máy này.");
      }

      let user;
      try {
        user = JSON.parse(localStorage.getItem("cloudstock_current_user") || "null");
      } catch {
        throw new Error("Không đọc được tài khoản mock hiện tại.");
      }
      if (!user || !["Admin", "Staff"].includes(user.role)) {
        throw new Error("Hãy đăng nhập bằng tài khoản Admin hoặc Staff trước.");
      }
      return `local-dev:${user.role}`;
    }

    const storage = CONFIG.USE_MOCK_AUTH ? localStorage : sessionStorage;
    return storage.getItem("cloudstock_id_token") || "";
  }

  async function _fetchAPI(method, path, body = null, additionalHeaders = {}) {
    const url = `${CONFIG.API_BASE_URL}${path}`;
    const headers = {
      "Content-Type": "application/json",
      Authorization: `Bearer ${_getToken()}`,
      ...additionalHeaders,
    };

    const options = { method, headers };
    if (body !== null) {
      options.body = JSON.stringify(body);
    }

    const response = await fetch(url, options);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.message || `API Error: ${response.status} ${response.statusText}`
      );
    }

    // 204 No Content
    if (response.status === 204) return null;
    return response.json();
  }

  async function _fetchAllPages(path) {
    const data = [];
    let nextToken = null;

    do {
      const params = new URLSearchParams({
        limit: String(Math.min(CONFIG.PAGE_SIZE || 100, 100)),
      });
      if (nextToken) params.set("nextToken", nextToken);

      const separator = path.includes("?") ? "&" : "?";
      const response = await _fetchAPI("GET", `${path}${separator}${params}`);
      if (!response || !Array.isArray(response.data)) {
        throw new Error("API trả về danh sách không đúng định dạng.");
      }

      data.push(...response.data);
      nextToken = response.nextToken || null;
    } while (nextToken);

    return _wrapResponse(data);
  }

  function _wrapResponse(data) {
    return { success: true, data };
  }


  const ID_FIELD_MAP = {
    users: "id",
    suppliers: "supplierId",
    products: "productId",
    transactions: "transactionId",
    systemLogs: "timestamp", 
  };

  async function _mockGetAll(collection) {
    await _delay();
    return _wrapResponse(MockDataStore.getAll(collection));
  }

  async function _mockGetById(collection, id) {
    await _delay();
    const idField = ID_FIELD_MAP[collection];
    const record = MockDataStore.getById(collection, idField, id);
    if (!record) throw new Error(`Khong tim thay ban ghi: ${id}`);
    return _wrapResponse(record);
  }

  async function _mockCreate(collection, record) {
    await _delay();
    const created = MockDataStore.add(collection, record);
    return _wrapResponse(created);
  }

  async function _mockUpdate(collection, id, updates) {
    await _delay();
    const idField = ID_FIELD_MAP[collection];
    const updated = MockDataStore.update(collection, idField, id, updates);
    if (!updated) throw new Error(`Khong tim thay ban ghi de cap nhat: ${id}`);
    return _wrapResponse(updated);
  }

  async function _mockDelete(collection, id) {
    await _delay();
    const idField = ID_FIELD_MAP[collection];
    const success = MockDataStore.remove(collection, idField, id);
    if (!success) throw new Error(`Khong tim thay ban ghi de xoa: ${id}`);
    return _wrapResponse({ deleted: true });
  }

  const Products = {
    async getAll() {
      if (_usesMockData("products")) return _mockGetAll("products");
      return _fetchAllPages("/products");
    },

    async getById(productId) {
      if (_usesMockData("products")) return _mockGetById("products", productId);
      return _fetchAPI("GET", `/products/${productId}`);
    },

    async create(product) {
      if (_usesMockData("products")) return _mockCreate("products", product);
      if (product.imageUrl) {
        throw new Error("Tải ảnh sản phẩm lên backend chưa được hỗ trợ; hãy bỏ ảnh đính kèm.");
      }
      return _fetchAPI("POST", "/products", product);
    },

    async update(productId, updates) {
      if (_usesMockData("products")) return _mockUpdate("products", productId, updates);
      if (updates.imageUrl) {
        throw new Error("Tải ảnh sản phẩm lên backend chưa được hỗ trợ; hãy bỏ ảnh đính kèm.");
      }
      return _fetchAPI("PUT", `/products/${productId}`, updates);
    },

    async delete(productId) {
      if (_usesMockData("products")) return _mockDelete("products", productId);
      return _fetchAPI("DELETE", `/products/${productId}`);
    },

    async getLowStock() {
      if (_usesMockData("products")) {
        await _delay();
        const all = MockDataStore.getAll("products");
        const lowStock = all.filter((p) => p.quantity < p.minThreshold);
        return _wrapResponse(lowStock);
      }
      return _fetchAllPages("/products?filter=low-stock");
    },
  };

  const Suppliers = {
    async getAll() {
      if (_usesMockData("suppliers")) return _mockGetAll("suppliers");
      return _fetchAllPages("/suppliers");
    },

    async getById(supplierId) {
      if (_usesMockData("suppliers")) return _mockGetById("suppliers", supplierId);
      return _fetchAPI("GET", `/suppliers/${supplierId}`);
    },

    async create(supplier) {
      if (_usesMockData("suppliers")) return _mockCreate("suppliers", supplier);
      return _fetchAPI("POST", "/suppliers", supplier);
    },

    async update(supplierId, updates) {
      if (_usesMockData("suppliers")) return _mockUpdate("suppliers", supplierId, updates);
      return _fetchAPI("PUT", `/suppliers/${supplierId}`, updates);
    },

    async delete(supplierId) {
      if (_usesMockData("suppliers")) return _mockDelete("suppliers", supplierId);
      return _fetchAPI("DELETE", `/suppliers/${supplierId}`);
    },
  };

  const Transactions = {
    async getAll() {
      if (_usesMockData("transactions")) return _mockGetAll("transactions");
      return _fetchAllPages("/transactions");
    },

    async getById(transactionId) {
      if (_usesMockData("transactions"))
        return _mockGetById("transactions", transactionId);
      return _fetchAPI("GET", `/transactions/${transactionId}`);
    },

    async create(transaction) {
      if (_usesMockData("transactions")) {
        await _delay();
        // Cập nhật tồn kho
        const product = MockDataStore.getById(
          "products",
          "productId",
          transaction.productId
        );
        if (!product) throw new Error("San pham khong ton tai");

        const delta =
          transaction.type === "IN"
            ? transaction.amount
            : -transaction.amount;
        const newQuantity = product.quantity + delta;

        if (newQuantity < 0) {
          throw new Error(
            `Khong du ton kho. Hien co: ${product.quantity}, Yeu cau xuat: ${transaction.amount}`
          );
        }

        MockDataStore.update("products", "productId", transaction.productId, {
          quantity: newQuantity,
          updatedAt: new Date().toISOString(),
        });

        const created = MockDataStore.add("transactions", transaction);
        return _wrapResponse(created);
      }
      const idempotencyKey = transaction.idempotencyKey || transaction.transactionId;
      if (!idempotencyKey) {
        throw new Error("Giao dịch cần có Idempotency-Key để gửi an toàn.");
      }
      if (transaction.invoiceUrl) {
        throw new Error("Tải chứng từ lên backend chưa được hỗ trợ; hãy bỏ chứng từ đính kèm.");
      }
      const requestBody = {
        type: transaction.type,
        productId: transaction.productId,
        amount: transaction.amount,
        supplierId: transaction.supplierId || null,
        reason: transaction.reason,
      };
      if (transaction.invoiceKey) requestBody.invoiceKey = transaction.invoiceKey;
      return _fetchAPI("POST", "/transactions", requestBody, {
        "Idempotency-Key": String(idempotencyKey),
      });
    },
  };

  const Users = {
    async getAll() {
      if (_usesMockData("users")) return _mockGetAll("users");
      return _fetchAPI("GET", "/users");
    },

    async getById(userId) {
      if (_usesMockData("users")) return _mockGetById("users", userId);
      return _fetchAPI("GET", `/users/${userId}`);
    },

    async create(user) {
      if (_usesMockData("users")) return _mockCreate("users", user);
      return _fetchAPI("POST", "/users", user);
    },

    async update(userId, updates) {
      if (_usesMockData("users")) return _mockUpdate("users", userId, updates);
      return _fetchAPI("PUT", `/users/${userId}`, updates);
    },

    async delete(userId) {
      if (_usesMockData("users")) return _mockDelete("users", userId);
      return _fetchAPI("DELETE", `/users/${userId}`);
    },
  };

  const SystemLogs = {
    async getAll() {
      if (_usesMockData("systemLogs")) return _mockGetAll("systemLogs");
      return _fetchAPI("GET", "/logs");
    },
  };

  const Dashboard = {
    async getStats() {
      if (CONFIG.USE_MOCK_DATA) {
        let products;
        let transactions;
        let suppliers;
        if (CONFIG.USE_LOCAL_API) {
          const [productResponse, transactionResponse, supplierResponse] =
            await Promise.all([
              Products.getAll(),
              Transactions.getAll(),
              Suppliers.getAll(),
            ]);
          products = productResponse.data;
          transactions = transactionResponse.data;
          suppliers = supplierResponse.data;
        } else {
          await _delay();
          products = MockDataStore.getAll("products");
          transactions = MockDataStore.getAll("transactions");
          suppliers = MockDataStore.getAll("suppliers");
        }

        const totalProducts = products.length;
        const totalQuantity = products.reduce((sum, p) => sum + p.quantity, 0);
        const totalValue = products.reduce(
          (sum, p) => sum + p.quantity * p.price,
          0
        );
        const lowStockCount = products.filter(
          (p) => p.quantity < p.minThreshold
        ).length;
        const totalSuppliers = suppliers.length;

        const todayStr = new Date().toISOString().slice(0, 10);
        const todayTransactions = transactions.filter((t) =>
          t.timestamp.startsWith(todayStr)
        );
        const todayIn = todayTransactions
          .filter((t) => t.type === "IN")
          .reduce((sum, t) => sum + t.amount, 0);
        const todayOut = todayTransactions
          .filter((t) => t.type === "OUT")
          .reduce((sum, t) => sum + t.amount, 0);

        return _wrapResponse({
          totalProducts,
          totalQuantity,
          totalValue,
          lowStockCount,
          totalSuppliers,
          todayIn,
          todayOut,
          todayTransactions: todayTransactions.length,
        });
      }
      return _fetchAPI("GET", "/dashboard/stats");
    },
  };

  const HOSTED_SESSION_KEYS = [
    "cloudstock_id_token",
    "cloudstock_oauth_state",
    "cloudstock_pkce_verifier",
  ];

  function getHostedUiSettings() {
    let domain;
    let redirectUri;
    let logoutUri;
    try {
      domain = new URL(CONFIG.COGNITO_HOSTED_UI_DOMAIN);
      redirectUri = new URL(CONFIG.COGNITO_REDIRECT_URI);
      logoutUri = new URL(CONFIG.COGNITO_LOGOUT_URI);
    } catch {
      throw new Error("Cognito Hosted UI domain hoặc URL callback chưa được cấu hình.");
    }

    if (
      domain.protocol !== "https:" ||
      domain.pathname !== "/" ||
      domain.search ||
      domain.hash ||
      !CONFIG.COGNITO_CLIENT_ID
    ) {
      throw new Error("Cognito Hosted UI domain hoặc Client ID chưa được cấu hình hợp lệ.");
    }

    return {
      domain: domain.origin,
      clientId: CONFIG.COGNITO_CLIENT_ID,
      redirectUri: redirectUri.href,
      logoutUri: logoutUri.href,
      scopes: CONFIG.COGNITO_SCOPES.join(" "),
    };
  }

  function encodeBase64Url(bytes) {
    let binary = "";
    bytes.forEach((byte) => {
      binary += String.fromCharCode(byte);
    });
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  }

  function createRandomValue(byteLength = 32) {
    if (!window.crypto?.getRandomValues) {
      throw new Error("Trình duyệt không hỗ trợ tạo dữ liệu đăng nhập an toàn.");
    }
    const bytes = new Uint8Array(byteLength);
    window.crypto.getRandomValues(bytes);
    return encodeBase64Url(bytes);
  }

  async function createPkceChallenge(verifier) {
    if (!window.crypto?.subtle) {
      throw new Error("Trình duyệt cần HTTPS hoặc localhost để đăng nhập an toàn.");
    }
    const digest = await window.crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(verifier)
    );
    return encodeBase64Url(new Uint8Array(digest));
  }

  async function beginHostedUiLogin() {
    const settings = getHostedUiSettings();
    const state = createRandomValue();
    const verifier = createRandomValue();
    const challenge = await createPkceChallenge(verifier);
    sessionStorage.setItem("cloudstock_oauth_state", state);
    sessionStorage.setItem("cloudstock_pkce_verifier", verifier);

    const params = new URLSearchParams({
      client_id: settings.clientId,
      response_type: "code",
      scope: settings.scopes,
      redirect_uri: settings.redirectUri,
      code_challenge_method: "S256",
      code_challenge: challenge,
      state,
    });
    window.location.assign(`${settings.domain}/oauth2/authorize?${params}`);
  }

  function clearHostedUiSession() {
    HOSTED_SESSION_KEYS.forEach((key) => sessionStorage.removeItem(key));
  }

  function decodeIdToken(token) {
    const parts = token.split(".");
    if (parts.length !== 3) throw new Error("ID token Cognito không hợp lệ.");

    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
    const binary = atob(padded);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  }

  function userFromIdToken(token) {
    const claims = decodeIdToken(token);
    if (
      typeof claims.sub !== "string" ||
      !Number.isFinite(claims.exp) ||
      claims.exp * 1000 <= Date.now()
    ) {
      return null;
    }

    const rawGroups = claims["cognito:groups"] || [];
    const groups = Array.isArray(rawGroups)
      ? rawGroups
      : String(rawGroups).split(",").map((group) => group.trim());
    const role = groups.find((group) => group === "Admin" || group === "Staff");
    if (!role) return null;

    const username =
      claims.preferred_username ||
      claims["cognito:username"] ||
      claims.username ||
      claims.email ||
      claims.sub;
    return {
      id: claims.sub,
      username,
      fullName: claims.name || username,
      email: claims.email || "",
      role,
      status: "ACTIVE",
    };
  }

  function getHostedUiUser() {
    const token = sessionStorage.getItem("cloudstock_id_token");
    if (!token) return null;
    try {
      const user = userFromIdToken(token);
      if (!user) clearHostedUiSession();
      return user;
    } catch {
      clearHostedUiSession();
      return null;
    }
  }

  async function handleHostedUiCallback() {
    const callbackUrl = new URL(window.location.href);
    const code = callbackUrl.searchParams.get("code");
    const oauthError = callbackUrl.searchParams.get("error");
    if (!code && !oauthError) return false;

    const returnedState = callbackUrl.searchParams.get("state");
    const expectedState = sessionStorage.getItem("cloudstock_oauth_state");
    const verifier = sessionStorage.getItem("cloudstock_pkce_verifier");
    window.history.replaceState({}, document.title, callbackUrl.pathname);
    sessionStorage.removeItem("cloudstock_oauth_state");
    sessionStorage.removeItem("cloudstock_pkce_verifier");

    if (oauthError) {
      throw new Error(
        callbackUrl.searchParams.get("error_description") || oauthError
      );
    }
    if (!expectedState || returnedState !== expectedState || !verifier) {
      throw new Error("OAuth state không hợp lệ; hãy thử đăng nhập lại.");
    }

    const settings = getHostedUiSettings();
    const response = await fetch(`${settings.domain}/oauth2/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        client_id: settings.clientId,
        code,
        redirect_uri: settings.redirectUri,
        code_verifier: verifier,
      }),
    });
    const tokenResponse = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(
        tokenResponse.error_description ||
          tokenResponse.error ||
          `Cognito token exchange failed (${response.status}).`
      );
    }
    if (!tokenResponse.id_token) {
      throw new Error("Cognito không trả về ID token.");
    }

    let user;
    try {
      user = userFromIdToken(tokenResponse.id_token);
    } catch {
      throw new Error("Không thể đọc thông tin người dùng từ ID token.");
    }
    if (!user) {
      throw new Error("Tài khoản Cognito cần thuộc nhóm Admin hoặc Staff.");
    }

    clearHostedUiSession();
    sessionStorage.setItem("cloudstock_id_token", tokenResponse.id_token);
    return true;
  }

  function logoutFromHostedUi() {
    const settings = getHostedUiSettings();
    clearHostedUiSession();
    const params = new URLSearchParams({
      client_id: settings.clientId,
      logout_uri: settings.logoutUri,
    });
    return `${settings.domain}/logout?${params}`;
  }

  const Auth = {
    async login(username, password) {
      if (CONFIG.USE_MOCK_AUTH) {
        await _delay();
        const users = MockDataStore.getAll("users");
        const user = users.find((u) => u.username === username);

        if (!user) throw new Error("Tai khoan khong ton tai");
        if (user.status === "LOCKED") throw new Error("Tai khoan da bi khoa");

        const mockToken = btoa(
          JSON.stringify({ sub: user.id, username: user.username })
        );
        localStorage.setItem("cloudstock_id_token", mockToken);
        localStorage.setItem("cloudstock_current_user", JSON.stringify(user));
        return _wrapResponse({ user, token: mockToken });
      }
      return beginHostedUiLogin();
    },

    logout() {
      if (CONFIG.USE_MOCK_AUTH) {
        localStorage.removeItem("cloudstock_id_token");
        localStorage.removeItem("cloudstock_current_user");
        return null;
      }
      return logoutFromHostedUi();
    },

    isAuthenticated() {
      return CONFIG.USE_MOCK_AUTH
        ? !!localStorage.getItem("cloudstock_id_token")
        : !!getHostedUiUser();
    },

    getCurrentUser() {
      if (!CONFIG.USE_MOCK_AUTH) return getHostedUiUser();
      const raw = localStorage.getItem("cloudstock_current_user");
      return raw ? JSON.parse(raw) : null;
    },

    handleHostedUiCallback() {
      return handleHostedUiCallback();
    },
  };

  return {
    Products,
    Suppliers,
    Transactions,
    Users,
    SystemLogs,
    Dashboard,
    Auth,
  };
})();

