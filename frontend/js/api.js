const ApiService = (() => {
  function _delay(ms = CONFIG.MOCK_DELAY_MS) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function _getToken() {
    return localStorage.getItem("cloudstock_id_token") || "";
  }

  async function _fetchAPI(method, path, body = null) {
    const url = `${CONFIG.API_BASE_URL}${path}`;
    const headers = {
      "Content-Type": "application/json",
      Authorization: `Bearer ${_getToken()}`,
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
      if (CONFIG.USE_MOCK_DATA) return _mockGetAll("products");
      return _fetchAPI("GET", "/products");
    },

    async getById(productId) {
      if (CONFIG.USE_MOCK_DATA) return _mockGetById("products", productId);
      return _fetchAPI("GET", `/products/${productId}`);
    },

    async create(product) {
      if (CONFIG.USE_MOCK_DATA) return _mockCreate("products", product);
      return _fetchAPI("POST", "/products", product);
    },

    async update(productId, updates) {
      if (CONFIG.USE_MOCK_DATA) return _mockUpdate("products", productId, updates);
      return _fetchAPI("PUT", `/products/${productId}`, updates);
    },

    async delete(productId) {
      if (CONFIG.USE_MOCK_DATA) return _mockDelete("products", productId);
      return _fetchAPI("DELETE", `/products/${productId}`);
    },

    async getLowStock() {
      if (CONFIG.USE_MOCK_DATA) {
        await _delay();
        const all = MockDataStore.getAll("products");
        const lowStock = all.filter((p) => p.quantity < p.minThreshold);
        return _wrapResponse(lowStock);
      }
      return _fetchAPI("GET", "/products?filter=low-stock");
    },
  };

  const Suppliers = {
    async getAll() {
      if (CONFIG.USE_MOCK_DATA) return _mockGetAll("suppliers");
      return _fetchAPI("GET", "/suppliers");
    },

    async getById(supplierId) {
      if (CONFIG.USE_MOCK_DATA) return _mockGetById("suppliers", supplierId);
      return _fetchAPI("GET", `/suppliers/${supplierId}`);
    },

    async create(supplier) {
      if (CONFIG.USE_MOCK_DATA) return _mockCreate("suppliers", supplier);
      return _fetchAPI("POST", "/suppliers", supplier);
    },

    async update(supplierId, updates) {
      if (CONFIG.USE_MOCK_DATA) return _mockUpdate("suppliers", supplierId, updates);
      return _fetchAPI("PUT", `/suppliers/${supplierId}`, updates);
    },

    async delete(supplierId) {
      if (CONFIG.USE_MOCK_DATA) return _mockDelete("suppliers", supplierId);
      return _fetchAPI("DELETE", `/suppliers/${supplierId}`);
    },
  };

  const Transactions = {
    async getAll() {
      if (CONFIG.USE_MOCK_DATA) return _mockGetAll("transactions");
      return _fetchAPI("GET", "/transactions");
    },

    async getById(transactionId) {
      if (CONFIG.USE_MOCK_DATA)
        return _mockGetById("transactions", transactionId);
      return _fetchAPI("GET", `/transactions/${transactionId}`);
    },

    async create(transaction) {
      if (CONFIG.USE_MOCK_DATA) {
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
      return _fetchAPI("POST", "/transactions", transaction);
    },
  };

  const Users = {
    async getAll() {
      if (CONFIG.USE_MOCK_DATA) return _mockGetAll("users");
      return _fetchAPI("GET", "/users");
    },

    async getById(userId) {
      if (CONFIG.USE_MOCK_DATA) return _mockGetById("users", userId);
      return _fetchAPI("GET", `/users/${userId}`);
    },

    async create(user) {
      if (CONFIG.USE_MOCK_DATA) return _mockCreate("users", user);
      return _fetchAPI("POST", "/users", user);
    },

    async update(userId, updates) {
      if (CONFIG.USE_MOCK_DATA) return _mockUpdate("users", userId, updates);
      return _fetchAPI("PUT", `/users/${userId}`, updates);
    },

    async delete(userId) {
      if (CONFIG.USE_MOCK_DATA) return _mockDelete("users", userId);
      return _fetchAPI("DELETE", `/users/${userId}`);
    },
  };

  const SystemLogs = {
    async getAll() {
      if (CONFIG.USE_MOCK_DATA) return _mockGetAll("systemLogs");
      return _fetchAPI("GET", "/logs");
    },
  };

  const Dashboard = {
    async getStats() {
      if (CONFIG.USE_MOCK_DATA) {
        await _delay();
        const products = MockDataStore.getAll("products");
        const transactions = MockDataStore.getAll("transactions");
        const suppliers = MockDataStore.getAll("suppliers");

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

  const Auth = {
    async login(username, password) {
      if (CONFIG.USE_MOCK_DATA) {
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
      return _fetchAPI("POST", "/auth/login", { username, password });
    },

    logout() {
      localStorage.removeItem("cloudstock_id_token");
      localStorage.removeItem("cloudstock_current_user");
    },

    isAuthenticated() {
      return !!localStorage.getItem("cloudstock_id_token");
    },

    getCurrentUser() {
      const raw = localStorage.getItem("cloudstock_current_user");
      return raw ? JSON.parse(raw) : null;
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

