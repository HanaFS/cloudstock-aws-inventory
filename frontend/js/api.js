const ApiService = (() => {
  const LOCAL_API_RESOURCES = new Set(["products", "suppliers", "transactions"]);

  function _delay(ms = (typeof CONFIG !== "undefined" && CONFIG.MOCK_DELAY_MS) || 0) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function _usesMockData(resource) {
    return (
      typeof MockDataStore !== "undefined" &&
      typeof CONFIG !== "undefined" &&
      CONFIG.USE_MOCK_DATA &&
      !(CONFIG.USE_LOCAL_API && LOCAL_API_RESOURCES.has(resource))
    );
  }

  function _getToken() {
    return (
      localStorage.getItem("id_token") ||
      localStorage.getItem("cloudstock_id_token") ||
      sessionStorage.getItem("cloudstock_id_token") ||
      ""
    );
  }

  async function _fetchAPI(method, path, body = null, additionalHeaders = {}) {
    const isLocal = typeof CONFIG !== "undefined" && CONFIG.USE_LOCAL_API;
    const baseUrl = isLocal
      ? ((typeof CONFIG !== "undefined" && CONFIG.API_BASE_URL) || "http://localhost:3001")
      : (typeof AWS_CONFIG !== "undefined" && AWS_CONFIG.API_BASE_URL) ||
        (typeof CONFIG !== "undefined" && CONFIG.API_BASE_URL) ||
        "";
    const url = `${baseUrl}${path}`;
    const token = _getToken();
    const headers = {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
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
        errorData.message || `Lỗi API: ${response.status} ${response.statusText}`
      );
    }

    if (response.status === 204) return null;
    return response.json();
  }

  async function _fetchAllPages(path) {
    const response = await _fetchAPI("GET", path);
    let items = [];
    if (Array.isArray(response)) {
      items = response;
    } else if (response && Array.isArray(response.data)) {
      items = response.data;
    } else if (response && typeof response === "object") {
      items = [response];
    }
    return _wrapResponse(items);
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
    if (typeof MockDataStore === "undefined") return _wrapResponse([]);
    await _delay();
    return _wrapResponse(MockDataStore.getAll(collection));
  }

  async function _mockGetById(collection, id) {
    if (typeof MockDataStore === "undefined") throw new Error(`Không tìm thấy bản ghi: ${id}`);
    await _delay();
    const idField = ID_FIELD_MAP[collection];
    const record = MockDataStore.getById(collection, idField, id);
    if (!record) throw new Error(`Không tìm thấy bản ghi: ${id}`);
    return _wrapResponse(record);
  }

  async function _mockCreate(collection, record) {
    if (typeof MockDataStore === "undefined") return _wrapResponse(record);
    await _delay();
    const created = MockDataStore.add(collection, record);
    return _wrapResponse(created);
  }

  async function _mockUpdate(collection, id, updates) {
    if (typeof MockDataStore === "undefined") return _wrapResponse(updates);
    await _delay();
    const idField = ID_FIELD_MAP[collection];
    const updated = MockDataStore.update(collection, idField, id, updates);
    if (!updated) throw new Error(`Không tìm thấy bản ghi để cập nhật: ${id}`);
    return _wrapResponse(updated);
  }

  async function _mockDelete(collection, id) {
    if (typeof MockDataStore === "undefined") return _wrapResponse({ deleted: true });
    await _delay();
    const idField = ID_FIELD_MAP[collection];
    const success = MockDataStore.remove(collection, idField, id);
    if (!success) throw new Error(`Không tìm thấy bản ghi để xóa: ${id}`);
    return _wrapResponse({ deleted: true });
  }

  const Products = {
    async getAll() {
      if (_usesMockData("products")) return _mockGetAll("products");
      const res = await _fetchAllPages("/products");
      if (Array.isArray(res.data)) {
        res.data.forEach((p) => {
          if (p.quantity === undefined && p.stockQuantity !== undefined) {
            p.quantity = p.stockQuantity;
          }
          if (p.stockQuantity === undefined && p.quantity !== undefined) {
            p.stockQuantity = p.quantity;
          }
        });
      }
      return res;
    },

    async getById(productId) {
      if (_usesMockData("products")) return _mockGetById("products", productId);
      const res = await _fetchAPI("GET", `/products/${productId}`);
      const p = (res && res.data) ? res.data : res;
      if (p) {
        if (p.quantity === undefined && p.stockQuantity !== undefined) p.quantity = p.stockQuantity;
        if (p.stockQuantity === undefined && p.quantity !== undefined) p.stockQuantity = p.quantity;
      }
      return _wrapResponse(p);
    },

    async create(product) {
      if (_usesMockData("products")) return _mockCreate("products", product);
      const payload = {
        name: product.name,
        category: product.category,
        price: Number(product.price) || 0,
        stockQuantity: Number(product.stockQuantity ?? product.quantity) || 0,
        minThreshold: Number(product.minThreshold) || 5,
        imageUrl: product.imageUrl || "",
      };
      const res = await _fetchAPI("POST", "/products", payload);
      const created = (res && res.data) ? res.data : res;
      if (created) {
        if (created.quantity === undefined && created.stockQuantity !== undefined) {
          created.quantity = created.stockQuantity;
        }
      }
      return _wrapResponse(created);
    },

    async update(productId, updates) {
      if (_usesMockData("products")) return _mockUpdate("products", productId, updates);
      const payload = { ...updates };
      if (payload.quantity !== undefined && payload.stockQuantity === undefined) {
        payload.stockQuantity = Number(payload.quantity);
      }
      if (payload.price !== undefined) payload.price = Number(payload.price);
      if (payload.stockQuantity !== undefined) payload.stockQuantity = Number(payload.stockQuantity);
      if (payload.minThreshold !== undefined) payload.minThreshold = Number(payload.minThreshold);
      const res = await _fetchAPI("PUT", `/products/${productId}`, payload);
      return _wrapResponse(res);
    },

    async delete(productId) {
      if (_usesMockData("products")) return _mockDelete("products", productId);
      const res = await _fetchAPI("DELETE", `/products/${productId}`);
      return _wrapResponse(res || { deleted: true });
    },

    async getLowStock() {
      if (_usesMockData("products")) {
        await _delay();
        const all = MockDataStore.getAll("products");
        const lowStock = all.filter((p) => (p.quantity || p.stockQuantity || 0) < (p.minThreshold || 0));
        return _wrapResponse(lowStock);
      }
      const allRes = await Products.getAll();
      const low = (allRes.data || []).filter((p) => (p.quantity || p.stockQuantity || 0) < (p.minThreshold || 0));
      return _wrapResponse(low);
    },

    async getUploadUrl(fileName, contentType = "image/jpeg", folder = "products") {
      return _fetchAPI("POST", "/products/upload-url", {
        folder,
        fileName,
        contentType,
      });
    },
  };

  const Suppliers = {
    async getAll() {
      if (_usesMockData("suppliers")) return _mockGetAll("suppliers");
      return _fetchAllPages("/suppliers");
    },

    async getById(supplierId) {
      if (_usesMockData("suppliers")) return _mockGetById("suppliers", supplierId);
      const res = await _fetchAPI("GET", `/suppliers/${supplierId}`);
      return _wrapResponse((res && res.data) ? res.data : res);
    },

    async create(supplier) {
      if (_usesMockData("suppliers")) return _mockCreate("suppliers", supplier);
      const payload = {
        name: supplier.name,
        phone: supplier.phone || "",
        address: supplier.address || "",
      };
      const res = await _fetchAPI("POST", "/suppliers", payload);
      return _wrapResponse((res && res.data) ? res.data : res);
    },

    async update(supplierId, updates) {
      if (_usesMockData("suppliers")) return _mockUpdate("suppliers", supplierId, updates);
      const res = await _fetchAPI("PUT", `/suppliers/${supplierId}`, updates);
      return _wrapResponse(res);
    },

    async delete(supplierId) {
      if (_usesMockData("suppliers")) return _mockDelete("suppliers", supplierId);
      const res = await _fetchAPI("DELETE", `/suppliers/${supplierId}`);
      return _wrapResponse(res || { deleted: true });
    },
  };

  const Transactions = {
    async getAll() {
      if (_usesMockData("transactions")) return _mockGetAll("transactions");
      const res = await _fetchAllPages("/transactions");
      if (Array.isArray(res.data)) {
        res.data.forEach((t) => {
          if (t.amount === undefined && t.quantity !== undefined) t.amount = t.quantity;
          if (t.quantity === undefined && t.amount !== undefined) t.quantity = t.amount;
          if (t.type === "IMPORT") t.type = "IN";
          else if (t.type === "EXPORT") t.type = "OUT";
        });
      }
      return res;
    },

    async getById(transactionId) {
      if (_usesMockData("transactions"))
        return _mockGetById("transactions", transactionId);
      const res = await _fetchAPI("GET", `/transactions/${transactionId}`);
      const t = (res && res.data) ? res.data : res;
      if (t) {
        if (t.amount === undefined && t.quantity !== undefined) t.amount = t.quantity;
        if (t.quantity === undefined && t.amount !== undefined) t.quantity = t.amount;
        if (t.type === "IMPORT") t.type = "IN";
        else if (t.type === "EXPORT") t.type = "OUT";
      }
      return _wrapResponse(t);
    },

    async create(transaction) {
      if (_usesMockData("transactions")) {
        await _delay();
        const product = MockDataStore.getById("products", "productId", transaction.productId);
        if (!product) throw new Error("Sản phẩm không tồn tại");
        const delta = transaction.type === "IN" ? transaction.amount : -transaction.amount;
        const newQuantity = (product.quantity || product.stockQuantity || 0) + delta;
        if (newQuantity < 0) {
          throw new Error(`Không đủ tồn kho. Hiện có: ${product.quantity}, Yêu cầu xuất: ${transaction.amount}`);
        }
        MockDataStore.update("products", "productId", transaction.productId, {
          quantity: newQuantity,
          stockQuantity: newQuantity,
          updatedAt: new Date().toISOString(),
        });
        const created = MockDataStore.add("transactions", transaction);
        return _wrapResponse(created);
      }

      const payload = {
        type: transaction.type,                                                          
        productId: transaction.productId,
        amount: Number(transaction.amount ?? transaction.quantity) || 0,                 
        supplierId: transaction.supplierId || null,
        reason: transaction.reason || transaction.fullReason || (transaction.type === "IN" ? "Nhập kho" : "Xuất kho"),
        invoiceKey: transaction.invoiceKey || null,                                      
      };

      const res = await _fetchAPI("POST", "/transactions", payload, {
        "Idempotency-Key": crypto.randomUUID(),                                          
      });
      return _wrapResponse(res);
    },

    async getInvoiceUrl(key) {
      return _fetchAPI("GET", `/transactions/invoice-url?key=${encodeURIComponent(key)}`);
    },
  };

  const Users = {
    async getAll() {
      if (_usesMockData("users")) return _mockGetAll("users");
      const res = await _fetchAllPages("/users");
      const list = Array.isArray(res.data) ? res.data : [];
      const mapped = list.map((u, idx) => ({
        id: u.id || u.sub || u.username || `u-${idx + 1}`,
        username: u.username || u.email,
        fullName: u.fullName || u.name || u.username || u.email,
        email: u.email || u.username,
        role: u.role || (u.groups && u.groups.includes("Admin") ? "Admin" : "Staff"),
        status: u.status || "ACTIVE",
        createdAt: u.createdAt,
      }));
      return _wrapResponse(mapped);
    },

    async getById(userId) {
      if (_usesMockData("users")) return _mockGetById("users", userId);
      const all = await Users.getAll();
      const user = (all.data || []).find((u) => u.id === userId || u.username === userId || u.email === userId);
      if (!user) throw new Error("Không tìm thấy người dùng");
      return _wrapResponse(user);
    },

    async create(user) {
      if (_usesMockData("users")) return _mockCreate("users", user);
      const payload = {
        email: user.email,
        password: user.password || "Staff@123",
        role: user.role || "Staff",
      };
      const res = await _fetchAPI("POST", "/users", payload);
      return _wrapResponse(res);
    },

    async update(userId, updates) {
      if (_usesMockData("users")) return _mockUpdate("users", userId, updates);
      if (updates.role) {
        const username = userId.includes("@") ? userId : userId;
        const res = await _fetchAPI("PUT", `/users/${encodeURIComponent(username)}/role`, { role: updates.role });
        return _wrapResponse(res);
      }
      return _wrapResponse({ message: "Updated" });
    },

    async delete(userId) {
      if (_usesMockData("users")) return _mockDelete("users", userId);
      const res = await _fetchAPI("DELETE", `/users/${encodeURIComponent(userId)}`);
      return _wrapResponse(res || { message: "Deleted" });
    },
  };

  const SystemLogs = {
    async getAll() {
      if (_usesMockData("systemLogs")) return _mockGetAll("systemLogs");
      try {
        const res = await _fetchAPI("GET", "/transactions/logs");
        const list = Array.isArray(res) ? res : (Array.isArray(res?.data) ? res.data : []);
        return _wrapResponse(list);
      } catch (err) {
        try {
          const res = await _fetchAPI("GET", "/logs");
          const list = Array.isArray(res) ? res : (Array.isArray(res?.data) ? res.data : []);
          return _wrapResponse(list);
        } catch {
          return _wrapResponse([]);
        }
      }
    },
  };

  const Dashboard = {
    async getStats() {
      if (_usesMockData("products")) {
        const products = MockDataStore.getAll("products");
        const transactions = MockDataStore.getAll("transactions");
        const suppliers = MockDataStore.getAll("suppliers");
        const totalProducts = products.length;
        const totalQuantity = products.reduce((sum, p) => sum + (p.quantity || 0), 0);
        const totalValue = products.reduce((sum, p) => sum + (p.quantity || 0) * (p.price || 0), 0);
        const lowStockCount = products.filter((p) => (p.quantity || 0) < (p.minThreshold || 0)).length;
        const totalSuppliers = suppliers.length;
        return _wrapResponse({
          totalProducts,
          totalQuantity,
          totalValue,
          lowStockCount,
          totalSuppliers,
          chartData: {
            importTotal: 0,
            exportTotal: 0,
            byCategory: [],
          },
        });
      }

      try {
        const res = await _fetchAPI("GET", "/dashboard");
        if (res && (res.totalProducts !== undefined || res.data?.totalProducts !== undefined)) {
          return _wrapResponse(res.data || res);
        }
      } catch (err) {
        console.warn("Direct /dashboard endpoint failed, calculating from resources:", err);
      }

      const [productsRes, transactionsRes, suppliersRes] = await Promise.all([
        Products.getAll(),
        Transactions.getAll(),
        Suppliers.getAll(),
      ]);

      const products = productsRes.data || [];
      const transactions = transactionsRes.data || [];
      const suppliers = suppliersRes.data || [];

      const totalProducts = products.length;
      const totalSuppliers = suppliers.length;
      const totalStockValue = products.reduce(
        (sum, p) => sum + (Number(p.price) || 0) * (Number(p.quantity ?? p.stockQuantity) || 0),
        0
      );
      const lowStockItems = products.filter(
        (p) => (Number(p.quantity ?? p.stockQuantity) || 0) < (Number(p.minThreshold) || 0)
      );
      const outOfStockItems = products.filter(
        (p) => (Number(p.quantity ?? p.stockQuantity) || 0) <= 0
      );
      const recentTransactions = transactions.slice(0, 10);

      const importTotal = transactions
        .filter((t) => t.type === "IN" || t.type === "IMPORT")
        .reduce((sum, t) => sum + (Number(t.amount ?? t.quantity) || 0), 0);
      const exportTotal = transactions
        .filter((t) => t.type === "OUT" || t.type === "EXPORT")
        .reduce((sum, t) => sum + (Number(t.amount ?? t.quantity) || 0), 0);

      return _wrapResponse({
        totalProducts,
        totalSuppliers,
        totalStockValue,
        lowStockCount: lowStockItems.length,
        outOfStockCount: outOfStockItems.length,
        lowStockItems,
        recentTransactions,
        chartData: {
          importTotal,
          exportTotal,
          byCategory: [],
        },
      });
    },
  };

  const HOSTED_SESSION_KEYS = [
    "cloudstock_oauth_state",
    "cloudstock_pkce_verifier",
  ];

  function clearHostedUiSession() {
    HOSTED_SESSION_KEYS.forEach((key) => sessionStorage.removeItem(key));
  }

  function decodeIdToken(token) {
    if (!token || typeof token !== "string") throw new Error("ID token không hợp lệ.");
    const parts = token.split(".");
    if (parts.length !== 3) throw new Error("ID token Cognito không đúng định dạng JWT.");

    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
    const binary = atob(padded);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  }

  function userFromIdToken(token) {
    try {
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
        : String(rawGroups).split(",").map((g) => g.trim());
      const role =
        groups.find((group) => group === "Admin" || group === "Staff") ||
        (groups.some((g) => /admin/i.test(g)) ? "Admin" : "Staff");

      const username =
        claims.email ||
        claims.preferred_username ||
        claims["cognito:username"] ||
        claims.username ||
        claims.sub;

      return {
        id: claims.sub,
        username,
        fullName: claims.name || claims.email || username,
        email: claims.email || username,
        role,
        status: "ACTIVE",
      };
    } catch {
      return null;
    }
  }

  async function handleHostedUiCallback() {
    return false;
  }

  const Auth = {
    async login(username, password) {
      if (typeof CONFIG !== "undefined" && CONFIG.USE_MOCK_AUTH && typeof MockDataStore !== "undefined") {
        await _delay();
        const users = MockDataStore.getAll("users");
        const user = users.find((u) => u.username === username || u.email === username);
        if (!user) throw new Error("Tài khoản không tồn tại");
        if (user.status === "LOCKED") throw new Error("Tài khoản đã bị khóa");
        const mockToken = btoa(JSON.stringify({ sub: user.id, username: user.username }));
        localStorage.setItem("id_token", mockToken);
        localStorage.setItem("cloudstock_id_token", mockToken);
        localStorage.setItem("cloudstock_current_user", JSON.stringify(user));
        return _wrapResponse({ user, token: mockToken });
      }

      const region =
        (typeof AWS_CONFIG !== "undefined" && AWS_CONFIG.REGION) || "ap-southeast-1";
      const userPoolId =
        (typeof AWS_CONFIG !== "undefined" && AWS_CONFIG.COGNITO?.USER_POOL_ID) ||
        (typeof CONFIG !== "undefined" && CONFIG.COGNITO_USER_POOL_ID) ||
        "ap-southeast-1_OnVjalo1T";
      const clientId =
        (typeof AWS_CONFIG !== "undefined" && AWS_CONFIG.COGNITO?.CLIENT_ID) ||
        (typeof CONFIG !== "undefined" && CONFIG.COGNITO_CLIENT_ID) ||
        "7qmk3hnllp292nguotfht8m7uh";

      let idToken = null;
      let accessToken = null;
      let refreshToken = null;

      // 1. Thử xác thực SRP (USER_SRP_AUTH) nếu SDK amazon-cognito-identity-js đã nạp
      if (typeof AmazonCognitoIdentity !== "undefined") {
        const pool = new AmazonCognitoIdentity.CognitoUserPool({
          UserPoolId: userPoolId,
          ClientId: clientId,
        });

        function srpAttempt(pwd) {
          return new Promise((resolve, reject) => {
            const authDetails = new AmazonCognitoIdentity.AuthenticationDetails({
              Username: username.trim(),
              Password: pwd,
            });
            const cognitoUser = new AmazonCognitoIdentity.CognitoUser({
              Username: username.trim(),
              Pool: pool,
            });

            cognitoUser.authenticateUser(authDetails, {
              onSuccess: (res) => {
                resolve({
                  idToken: res.getIdToken().getJwtToken(),
                  accessToken: res.getAccessToken().getJwtToken(),
                  refreshToken: res.getRefreshToken() ? res.getRefreshToken().getToken() : null,
                });
              },
              onFailure: (err) => {
                reject(err);
              },
              newPasswordRequired: (userAttributes) => {
                delete userAttributes.email_verified;
                delete userAttributes.phone_number_verified;
                cognitoUser.completeNewPasswordChallenge(pwd, userAttributes, {
                  onSuccess: (res) => {
                    resolve({
                      idToken: res.getIdToken().getJwtToken(),
                      accessToken: res.getAccessToken().getJwtToken(),
                      refreshToken: res.getRefreshToken() ? res.getRefreshToken().getToken() : null,
                    });
                  },
                  onFailure: (err) => {
                    reject(err);
                  },
                });
              },
            });
          });
        }

        try {
          const srpResult = await srpAttempt(password);
          idToken = srpResult.idToken;
          accessToken = srpResult.accessToken;
          refreshToken = srpResult.refreshToken;
        } catch (srpErr) {
          // Thử lại nếu có khả năng sai khoảng trắng đầu mật khẩu
          if (srpErr.name === "NotAuthorizedException") {
            try {
              const altPwd = password.startsWith(" ") ? password.trim() : " " + password;
              const srpResult = await srpAttempt(altPwd);
              idToken = srpResult.idToken;
              accessToken = srpResult.accessToken;
              refreshToken = srpResult.refreshToken;
            } catch (retryErr) {
              throw new Error("Sai email hoặc mật khẩu đăng nhập");
            }
          } else if (srpErr.name === "UserNotFoundException") {
            throw new Error("Tài khoản không tồn tại trên hệ thống Cognito");
          } else if (srpErr.name === "UserNotConfirmedException") {
            throw new Error("Tài khoản chưa được xác thực (kích hoạt) trên Cognito");
          } else {
            throw new Error(srpErr.message || "Đăng nhập Cognito SRP thất bại");
          }
        }
      } else {
        // 2. Dự phòng trực tiếp qua REST API (USER_PASSWORD_AUTH)
        const cognitoEndpoint = `https://cognito-idp.${region}.amazonaws.com/`;
        async function attemptAuth(pwd) {
          return fetch(cognitoEndpoint, {
            method: "POST",
            headers: {
              "Content-Type": "application/x-amz-json-1.1",
              "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
            },
            body: JSON.stringify({
              AuthFlow: "USER_PASSWORD_AUTH",
              ClientId: clientId,
              AuthParameters: {
                USERNAME: username.trim(),
                PASSWORD: pwd,
              },
            }),
          });
        }

        let resp = await attemptAuth(password);
        let data = await resp.json().catch(() => ({}));

        if (!resp.ok && data.__type === "NotAuthorizedException") {
          const altPwd = password.startsWith(" ") ? password.trim() : " " + password;
          const retryResp = await attemptAuth(altPwd);
          if (retryResp.ok) {
            resp = retryResp;
            data = await retryResp.json().catch(() => ({}));
          }
        }

        if (!resp.ok) {
          const errorMsg = data.message || "";
          if (errorMsg.includes("USER_PASSWORD_AUTH flow not enabled")) {
            throw new Error(
              "Client Cognito chưa bật flow USER_PASSWORD_AUTH. Vui lòng kết nối Internet để nạp thư viện SRP, hoặc bật ALLOW_USER_PASSWORD_AUTH trong AWS Cognito App Client."
            );
          } else if (data.__type === "UserNotFoundException") {
            throw new Error("Tài khoản không tồn tại trên hệ thống");
          } else if (data.__type === "NotAuthorizedException") {
            throw new Error("Sai email hoặc mật khẩu đăng nhập");
          } else if (data.__type === "UserNotConfirmedException") {
            throw new Error("Tài khoản chưa được kích hoạt");
          } else {
            throw new Error(data.message || `Đăng nhập Cognito thất bại (${resp.status})`);
          }
        }

        if (data.ChallengeName === "NEW_PASSWORD_REQUIRED") {
          try {
            const challengeResp = await fetch(cognitoEndpoint, {
              method: "POST",
              headers: {
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": "AWSCognitoIdentityProviderService.RespondToAuthChallenge",
              },
              body: JSON.stringify({
                ChallengeName: "NEW_PASSWORD_REQUIRED",
                ClientId: clientId,
                ChallengeResponses: {
                  USERNAME: username.trim(),
                  NEW_PASSWORD: password,
                },
                Session: data.Session,
              }),
            });
            if (challengeResp.ok) {
              data = await challengeResp.json();
            }
          } catch (e) {
            console.warn("Challenge handling error:", e);
          }
        }

        if (!data.AuthenticationResult || !data.AuthenticationResult.IdToken) {
          throw new Error("Cognito không trả về token xác thực hợp lệ.");
        }

        idToken = data.AuthenticationResult.IdToken;
        accessToken = data.AuthenticationResult.AccessToken;
        refreshToken = data.AuthenticationResult.RefreshToken;
      }

      const user = userFromIdToken(idToken);
      if (!user) {
        throw new Error("Tài khoản không thuộc nhóm quyền Admin hoặc Staff hợp lệ.");
      }

      localStorage.setItem("id_token", idToken);
      localStorage.setItem("cloudstock_id_token", idToken);
      if (accessToken) localStorage.setItem("access_token", accessToken);
      if (refreshToken) localStorage.setItem("refresh_token", refreshToken);
      localStorage.setItem("cloudstock_current_user", JSON.stringify(user));

      return _wrapResponse({ user, token: idToken });
    },

    logout() {
      localStorage.removeItem("id_token");
      localStorage.removeItem("cloudstock_id_token");
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      localStorage.removeItem("cloudstock_current_user");
      clearHostedUiSession();
      return null;
    },

    isAuthenticated() {
      const token =
        localStorage.getItem("id_token") ||
        localStorage.getItem("cloudstock_id_token") ||
        sessionStorage.getItem("cloudstock_id_token");
      if (!token) return false;
      const user = userFromIdToken(token);
      return !!user;
    },

    getCurrentUser() {
      const raw = localStorage.getItem("cloudstock_current_user");
      if (raw) {
        try {
          return JSON.parse(raw);
        } catch {}
      }
      const token =
        localStorage.getItem("id_token") ||
        localStorage.getItem("cloudstock_id_token");
      if (token) return userFromIdToken(token);
      return null;
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
window.ApiService = ApiService;