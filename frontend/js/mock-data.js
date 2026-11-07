const SEED_DATA = {
   
  users: [
    {
      id: "u-001",
      username: "admin.nguyen",
      fullName: "Nguyen Van An",
      email: "an.nguyen@cloudstock.vn",
      role: "Admin",
      status: "ACTIVE",
    },
    {
      id: "u-002",
      username: "staff.tran",
      fullName: "Tran Thi Bich",
      email: "bich.tran@cloudstock.vn",
      role: "Staff",
      status: "ACTIVE",
    },
    {
      id: "u-003",
      username: "staff.le",
      fullName: "Le Hoang Cuong",
      email: "cuong.le@cloudstock.vn",
      role: "Staff",
      status: "ACTIVE",
    },
    {
      id: "u-004",
      username: "staff.pham",
      fullName: "Pham Minh Duc",
      email: "duc.pham@cloudstock.vn",
      role: "Staff",
      status: "LOCKED",
    },
    {
      id: "u-005",
      username: "admin.vo",
      fullName: "Vo Thanh Em",
      email: "em.vo@cloudstock.vn",
      role: "Admin",
      status: "ACTIVE",
    },
  ],

   
  suppliers: [
    {
      supplierId: "sup-001",
      name: "Cong ty TNHH Thiet Bi Van Phong Minh Phat",
      phone: "028-3823-1001",
      address: "45 Nguyen Trai, Quan 1, TP.HCM",
    },
    {
      supplierId: "sup-002",
      name: "Cong ty CP Dien Tu Thanh Long",
      phone: "024-3856-2002",
      address: "112 Le Duan, Dong Da, Ha Noi",
    },
    {
      supplierId: "sup-003",
      name: "Cong ty TNHH Phu Kien So Viet Han",
      phone: "0236-382-3003",
      address: "78 Bach Dang, Hai Chau, Da Nang",
    },
    {
      supplierId: "sup-004",
      name: "Cong ty TNHH Noi That Hoa Phat",
      phone: "028-3920-4004",
      address: "200 Ly Thuong Kiet, Quan 10, TP.HCM",
    },
  ],

   
  products: [
    {
      productId: "prod-001",
      name: "Giay in A4 Double A 80gsm",
      category: "Van phong pham",
      quantity: 350,
      minThreshold: 100,
      price: 68000,
      supplierId: "sup-001",
      imageUrl: "",
      updatedAt: "2026-11-06T09:15:00Z",
    },
    {
      productId: "prod-002",
      name: "But bi Thien Long TL-027",
      category: "Van phong pham",
      quantity: 8,  
      minThreshold: 50,
      price: 4500,
      supplierId: "sup-001",
      imageUrl: "",
      updatedAt: "2026-11-06T08:30:00Z",
    },
    {
      productId: "prod-003",
      name: "Muc in HP 680 Black",
      category: "Linh kien",
      quantity: 12,  
      minThreshold: 20,
      price: 215000,
      supplierId: "sup-002",
      imageUrl: "",
      updatedAt: "2026-11-05T14:00:00Z",
    },
    {
      productId: "prod-004",
      name: "Ban phim co Logitech K845",
      category: "Thiet bi",
      quantity: 25,
      minThreshold: 10,
      price: 1490000,
      supplierId: "sup-002",
      imageUrl: "",
      updatedAt: "2026-11-05T11:20:00Z",
    },
    {
      productId: "prod-005",
      name: "Chuot khong day Logitech M331",
      category: "Thiet bi",
      quantity: 40,
      minThreshold: 15,
      price: 390000,
      supplierId: "sup-002",
      imageUrl: "",
      updatedAt: "2026-11-04T16:45:00Z",
    },
    {
      productId: "prod-006",
      name: "Man hinh Dell P2422H 24 inch",
      category: "Thiet bi",
      quantity: 5,  
      minThreshold: 8,
      price: 5290000,
      supplierId: "sup-002",
      imageUrl: "",
      updatedAt: "2026-11-04T10:10:00Z",
    },
    {
      productId: "prod-007",
      name: "Cap sac USB-C Anker 1.8m",
      category: "Phu kien",
      quantity: 3,  
      minThreshold: 30,
      price: 189000,
      supplierId: "sup-003",
      imageUrl: "",
      updatedAt: "2026-11-03T09:00:00Z",
    },
    {
      productId: "prod-008",
      name: "Tai nghe Bluetooth Sony WH-1000XM5",
      category: "Thiet bi",
      quantity: 15,
      minThreshold: 5,
      price: 6490000,
      supplierId: "sup-003",
      imageUrl: "",
      updatedAt: "2026-11-03T08:30:00Z",
    },
    {
      productId: "prod-009",
      name: "O cung SSD Samsung 870 EVO 500GB",
      category: "Linh kien",
      quantity: 22,
      minThreshold: 10,
      price: 1590000,
      supplierId: "sup-002",
      imageUrl: "",
      updatedAt: "2026-11-02T15:00:00Z",
    },
    {
      productId: "prod-010",
      name: "Ghe cong thai hoc Hoa Phat SG920",
      category: "Noi that",
      quantity: 18,
      minThreshold: 5,
      price: 3200000,
      supplierId: "sup-004",
      imageUrl: "",
      updatedAt: "2026-11-02T13:00:00Z",
    },
    {
      productId: "prod-011",
      name: "Den ban LED Xiaomi Mijia Lite",
      category: "Thiet bi",
      quantity: 30,
      minThreshold: 10,
      price: 450000,
      supplierId: "sup-003",
      imageUrl: "",
      updatedAt: "2026-11-01T10:00:00Z",
    },
    {
      productId: "prod-012",
      name: "Ke ho so 3 tang Deli 9848",
      category: "Van phong pham",
      quantity: 45,
      minThreshold: 15,
      price: 185000,
      supplierId: "sup-001",
      imageUrl: "",
      updatedAt: "2026-11-01T09:30:00Z",
    },
  ],

   
  transactions: [
    {
      transactionId: "txn-001",
      timestamp: "2026-11-06T08:00:00Z",
      performedBy: "staff.tran",
      type: "IN",
      productId: "prod-001",
      productName: "Giay in A4 Double A 80gsm",
      amount: 200,
      supplierId: "sup-001",
      reason: "Nhap hang dinh ky",
      invoiceUrl: "",
    },
    {
      transactionId: "txn-002",
      timestamp: "2026-11-06T09:15:00Z",
      performedBy: "staff.le",
      type: "OUT",
      productId: "prod-002",
      productName: "But bi Thien Long TL-027",
      amount: 42,
      supplierId: null,
      reason: "Cap phat cho phong Kinh doanh",
      invoiceUrl: "",
    },
    {
      transactionId: "txn-003",
      timestamp: "2026-11-06T10:30:00Z",
      performedBy: "admin.nguyen",
      type: "IN",
      productId: "prod-004",
      productName: "Ban phim co Logitech K845",
      amount: 10,
      supplierId: "sup-002",
      reason: "Bo sung thiet bi moi",
      invoiceUrl: "",
    },
    {
      transactionId: "txn-004",
      timestamp: "2026-11-05T08:45:00Z",
      performedBy: "staff.tran",
      type: "OUT",
      productId: "prod-005",
      productName: "Chuot khong day Logitech M331",
      amount: 5,
      supplierId: null,
      reason: "Cap phat cho nhan vien moi",
      invoiceUrl: "",
    },
    {
      transactionId: "txn-005",
      timestamp: "2026-11-05T11:20:00Z",
      performedBy: "staff.le",
      type: "IN",
      productId: "prod-003",
      productName: "Muc in HP 680 Black",
      amount: 15,
      supplierId: "sup-002",
      reason: "Dat hang bo sung",
      invoiceUrl: "",
    },
    {
      transactionId: "txn-006",
      timestamp: "2026-11-05T14:00:00Z",
      performedBy: "admin.nguyen",
      type: "OUT",
      productId: "prod-006",
      productName: "Man hinh Dell P2422H 24 inch",
      amount: 3,
      supplierId: null,
      reason: "Trang bi phong hop moi",
      invoiceUrl: "",
    },
    {
      transactionId: "txn-007",
      timestamp: "2026-11-04T09:00:00Z",
      performedBy: "staff.tran",
      type: "OUT",
      productId: "prod-007",
      productName: "Cap sac USB-C Anker 1.8m",
      amount: 25,
      supplierId: null,
      reason: "Cap phat cho team Ky thuat",
      invoiceUrl: "",
    },
    {
      transactionId: "txn-008",
      timestamp: "2026-11-04T10:30:00Z",
      performedBy: "staff.le",
      type: "IN",
      productId: "prod-008",
      productName: "Tai nghe Bluetooth Sony WH-1000XM5",
      amount: 10,
      supplierId: "sup-003",
      reason: "Nhap hang theo don dat",
      invoiceUrl: "",
    },
    {
      transactionId: "txn-009",
      timestamp: "2026-11-04T14:15:00Z",
      performedBy: "admin.nguyen",
      type: "OUT",
      productId: "prod-009",
      productName: "O cung SSD Samsung 870 EVO 500GB",
      amount: 5,
      supplierId: null,
      reason: "Nang cap may tram lam viec",
      invoiceUrl: "",
    },
    {
      transactionId: "txn-010",
      timestamp: "2026-11-03T08:30:00Z",
      performedBy: "staff.tran",
      type: "IN",
      productId: "prod-010",
      productName: "Ghe cong thai hoc Hoa Phat SG920",
      amount: 8,
      supplierId: "sup-004",
      reason: "Mua moi theo yeu cau",
      invoiceUrl: "",
    },
    {
      transactionId: "txn-011",
      timestamp: "2026-11-03T10:00:00Z",
      performedBy: "staff.le",
      type: "OUT",
      productId: "prod-001",
      productName: "Giay in A4 Double A 80gsm",
      amount: 50,
      supplierId: null,
      reason: "Cap phat cho phong Ke toan",
      invoiceUrl: "",
    },
    {
      transactionId: "txn-012",
      timestamp: "2026-11-02T09:00:00Z",
      performedBy: "admin.nguyen",
      type: "IN",
      productId: "prod-011",
      productName: "Den ban LED Xiaomi Mijia Lite",
      amount: 20,
      supplierId: "sup-003",
      reason: "Nhap lot hang moi",
      invoiceUrl: "",
    },
    {
      transactionId: "txn-013",
      timestamp: "2026-11-02T13:00:00Z",
      performedBy: "staff.tran",
      type: "OUT",
      productId: "prod-012",
      productName: "Ke ho so 3 tang Deli 9848",
      amount: 10,
      supplierId: null,
      reason: "Phan phoi cho cac phong ban",
      invoiceUrl: "",
    },
    {
      transactionId: "txn-014",
      timestamp: "2026-11-01T08:00:00Z",
      performedBy: "staff.le",
      type: "IN",
      productId: "prod-005",
      productName: "Chuot khong day Logitech M331",
      amount: 30,
      supplierId: "sup-002",
      reason: "Nhap hang dinh ky thang 11",
      invoiceUrl: "",
    },
    {
      transactionId: "txn-015",
      timestamp: "2026-11-01T15:30:00Z",
      performedBy: "admin.nguyen",
      type: "OUT",
      productId: "prod-003",
      productName: "Muc in HP 680 Black",
      amount: 8,
      supplierId: null,
      reason: "Thay muc may in tang 3",
      invoiceUrl: "",
    },
  ],

   
  systemLogs: [
    {
      timestamp: "2026-11-06T10:30:05Z",
      logStream: "lambda/inventoryService",
      level: "INFO",
      message:
        "POST /products/prod-004 - Nhap kho thanh cong: +10 Ban phim co Logitech K845",
    },
    {
      timestamp: "2026-11-06T10:29:58Z",
      logStream: "lambda/inventoryService",
      level: "INFO",
      message: "GET /products - Truy van danh sach san pham (page=1, size=10)",
    },
    {
      timestamp: "2026-11-06T09:15:12Z",
      logStream: "lambda/inventoryService",
      level: "WARN",
      message:
        "San pham prod-002 (But bi Thien Long TL-027) da xuong duoi nguong ton kho toi thieu: 8 < 50",
    },
    {
      timestamp: "2026-11-05T14:00:30Z",
      logStream: "lambda/inventoryService",
      level: "WARN",
      message:
        "San pham prod-006 (Man hinh Dell P2422H) da xuong duoi nguong ton kho toi thieu: 5 < 8",
    },
    {
      timestamp: "2026-11-05T11:20:15Z",
      logStream: "lambda/authService",
      level: "INFO",
      message:
        "Xac thuc thanh cong cho user staff.le tu IP 103.28.37.45",
    },
    {
      timestamp: "2026-11-04T16:00:00Z",
      logStream: "lambda/inventoryService",
      level: "ERROR",
      message:
        "Giao dich that bai: Khong du ton kho cho prod-007. Yeu cau: 50, Hien co: 3",
    },
    {
      timestamp: "2026-11-04T10:30:22Z",
      logStream: "lambda/inventoryService",
      level: "INFO",
      message:
        "POST /transactions/txn-008 - Nhap kho thanh cong: +10 Tai nghe Sony WH-1000XM5",
    },
    {
      timestamp: "2026-11-03T10:00:10Z",
      logStream: "lambda/reportService",
      level: "INFO",
      message:
        "Bao cao xuat kho duoc tao thanh cong. Tong so luong xuat: 50 (Giay in A4)",
    },
    {
      timestamp: "2026-11-02T09:05:00Z",
      logStream: "lambda/authService",
      level: "ERROR",
      message:
        "Dang nhap that bai cho user staff.pham - Tai khoan da bi khoa (LOCKED)",
    },
    {
      timestamp: "2026-11-01T08:00:05Z",
      logStream: "apigateway/access",
      level: "INFO",
      message:
        "Request ID abc-123-def: POST /transactions - 201 Created (latency: 245ms)",
    },
  ],
};

 



const MockDataStore = (() => {
  const STORAGE_KEY_PREFIX = "cloudstock_";
  const COLLECTIONS = Object.keys(SEED_DATA);

   




  function init(forceReset = false) {
    COLLECTIONS.forEach((collection) => {
      const key = STORAGE_KEY_PREFIX + collection;
      if (forceReset || localStorage.getItem(key) === null) {
        localStorage.setItem(
          key,
          JSON.stringify(SEED_DATA[collection])
        );
      }
    });
  }

   




  function getAll(collection) {
    const key = STORAGE_KEY_PREFIX + collection;
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : [];
  }

   
  function getById(collection, idField, idValue) {
    const items = getAll(collection);
    return items.find((item) => item[idField] === idValue) || null;
  }

   

  function add(collection, record) {
    const items = getAll(collection);
    items.push(record);
    _save(collection, items);
    return record;
  }


  function update(collection, idField, idValue, updates) {
    const items = getAll(collection);
    const index = items.findIndex((item) => item[idField] === idValue);
    if (index === -1) return null;
    items[index] = { ...items[index], ...updates };
    _save(collection, items);
    return items[index];
  }

   
  function remove(collection, idField, idValue) {
    const items = getAll(collection);
    const filtered = items.filter((item) => item[idField] !== idValue);
    if (filtered.length === items.length) return false;
    _save(collection, filtered);
    return true;
  }

   
  function resetAll() {
    init(true);
  }

  function _save(collection, data) {
    const key = STORAGE_KEY_PREFIX + collection;
    localStorage.setItem(key, JSON.stringify(data));
  }

  return { init, getAll, getById, add, update, remove, resetAll };
})();

 
MockDataStore.init();

