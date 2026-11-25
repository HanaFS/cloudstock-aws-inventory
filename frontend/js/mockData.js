// File: frontend/js/mockData.js
// Bộ dữ liệu mẫu từ backend/data phục vụ test local Nghiệp vụ Kho, Báo cáo & Logs

const MockDataStore = (() => {
  const STORAGE_PREFIX = "cloudstock_mock_";

  const DEFAULT_DATA = {
    suppliers: [
      { supplierId: "sup-001", name: "Công ty TNHH Phân Phối Công Nghệ FPT Synnex", phone: "02873006688", address: "Khu Công Nghệ Cao, TP. Thủ Đức, TP.HCM" },
      { supplierId: "sup-002", name: "Công ty CP Thế Giới Số Digiworld", phone: "02839290059", address: "Số 195-197 Nguyễn Thái Bình, Quận 1, TP.HCM" },
      { supplierId: "sup-003", name: "Công ty TNHH Tin Học Viễn Thông Viễn Sơn", phone: "02838326085", address: "Số 162 Bùi Thị Xuân, Quận 1, TP.HCM" },
      { supplierId: "sup-004", name: "Công ty CP Tập Đoàn Thiên Long", phone: "02837505555", address: "Lô 6-8-10-12 Đường số 3, KCN Tân Tạo, Bình Tân, TP.HCM" },
      { supplierId: "sup-005", name: "Công ty TNHH Thiết Bị Văn Phòng Lê Bảo Minh", phone: "02838386666", address: "Số 184 Nam Kỳ Khởi Nghĩa, Quận 3, TP.HCM" },
      { supplierId: "sup-006", name: "Công ty TNHH Kỹ Thuật Mạng Ánh Minh", phone: "02862914588", address: "Số 458 Nguyễn Thị Minh Khai, Quận 3, TP.HCM" },
      { supplierId: "sup-007", name: "Công ty CP Công Nghệ An Ninh Nhà An Toàn", phone: "02838685689", address: "Số 299/3 Lý Thường Kiệt, Quận 11, TP.HCM" },
      { supplierId: "sup-008", name: "Công ty TNHH Phụ Kiện Số Hoàng Hà", phone: "02839102244", address: "Số 112 Cách Mạng Tháng Tám, Quận 3, TP.HCM" },
      { supplierId: "sup-009", name: "Công ty TNHH Giấy & VPP Ánh Dương", phone: "02838119922", address: "Số 78 Cộng Hòa, Quận Tân Bình, TP.HCM" },
      { supplierId: "sup-010", name: "Công ty CP Nội Thất Văn Phòng Hòa Phát Miền Nam", phone: "02835111226", address: "Số 55 Bạch Đằng, Quận Bình Thạnh, TP.HCM" },
      { supplierId: "sup-011", name: "Công ty TNHH Thiết Bị Điện Công Nghiệp Phương Nam", phone: "02838994411", address: "Số 320 Điện Biên Phủ, Quận Bình Thạnh, TP.HCM" },
      { supplierId: "sup-012", name: "Công ty TNHH Giải Pháp Nghe Nhìn Sao Mai", phone: "02839307788", address: "Số 88 Võ Văn Tần, Quận 3, TP.HCM" },
      { supplierId: "sup-013", name: "Công ty TNHH Vật Tư & Cơ Khí Tân Tiến", phone: "02837651199", address: "Quốc lộ 1A, Quận Bình Tân, TP.HCM" },
      { supplierId: "sup-014", name: "Công ty CP Thiết Bị Điện & Chiếu Sáng Rạng Đông HCM", phone: "02838443355", address: "Số 215 Hoàng Văn Thụ, Quận Phú Nhuận, TP.HCM" },
      { supplierId: "sup-015", name: "Công ty TNHH Bảo Hộ Lao Động An Toàn Việt", phone: "02838158899", address: "Số 340 Trường Chinh, Quận Tân Bình, TP.HCM" },
    ],

    products: [
      { productId: "prod-0001", name: "Màn hình máy tính LG 23.8 inch IPS 2K QHD 165Hz", category: "Máy tính & Laptop", price: 4180000, quantity: 42, stockQuantity: 42, minThreshold: 25, status: "IN_STOCK", supplierId: "sup-001", imageUrl: "", updatedAt: "2026-11-06T13:40:00.000Z" },
      { productId: "prod-0002", name: "Máy in mã vạch tem nhãn Epson HL-L2321D", category: "Thiết bị văn phòng", price: 4870000, quantity: 20, stockQuantity: 20, minThreshold: 50, status: "IN_STOCK", supplierId: "sup-001", imageUrl: "", updatedAt: "2026-11-07T00:21:00.000Z" },
      { productId: "prod-0003", name: "Ổ cứng SSD Kingston 2TB M.2 NVMe PCIe Gen3", category: "Linh kiện PC", price: 2040000, quantity: 21, stockQuantity: 21, minThreshold: 20, status: "IN_STOCK", supplierId: "sup-006", imageUrl: "", updatedAt: "2026-10-24T19:28:00.000Z" },
      { productId: "prod-0004", name: "Router cân bằng tải Ubiquiti EAP650", category: "Thiết bị mạng", price: 4990000, quantity: 184, stockQuantity: 184, minThreshold: 50, status: "IN_STOCK", supplierId: "sup-006", imageUrl: "", updatedAt: "2026-10-13T21:31:00.000Z" },
      { productId: "prod-0005", name: "Ổ cứng di động SSD gắn ngoài HyperX 1TB", category: "Phụ kiện công nghệ", price: 4130000, quantity: 39, stockQuantity: 39, minThreshold: 30, status: "IN_STOCK", supplierId: "sup-008", imageUrl: "", updatedAt: "2026-11-06T15:16:00.000Z" },
      { productId: "prod-0006", name: "Bìa còng bật PaperOne gáy 5cm khổ A4", category: "Văn phòng phẩm", price: 54000, quantity: 6, stockQuantity: 6, minThreshold: 5, status: "IN_STOCK", supplierId: "sup-009", imageUrl: "", updatedAt: "2026-11-08T20:32:00.000Z" },
      { productId: "prod-0007", name: "Bộ 4 chai mực in phun màu Canon mã 003", category: "Vật tư tiêu hao", price: 608000, quantity: 21, stockQuantity: 21, minThreshold: 15, status: "IN_STOCK", supplierId: "sup-005", imageUrl: "", updatedAt: "2026-10-26T12:35:00.000Z" },
      { productId: "prod-0008", name: "Camera IP Thân ngoài trời Hikvision 2MP Full HD hồng ngoại 30m", category: "Thiết bị an ninh & Camera", price: 1500000, quantity: 4, stockQuantity: 4, minThreshold: 5, status: "IN_STOCK", supplierId: "sup-012", imageUrl: "", updatedAt: "2026-10-17T04:58:00.000Z" },
      { productId: "prod-0009", name: "Tủ hồ sơ sắt 2 cánh kính Ergolife SM1830", category: "Nội thất văn phòng", price: 3020000, quantity: 61, stockQuantity: 61, minThreshold: 20, status: "IN_STOCK", supplierId: "sup-013", imageUrl: "", updatedAt: "2026-11-18T22:02:00.000Z" },
      { productId: "prod-0010", name: "Bộ lưu điện UPS Offline Rạng Đông 1500VA/900W", category: "Thiết bị điện & Chiếu sáng", price: 4410000, quantity: 0, stockQuantity: 0, minThreshold: 20, status: "OUT_OF_STOCK", supplierId: "sup-014", imageUrl: "", updatedAt: "2026-10-22T09:43:00.000Z" },
      { productId: "prod-0011", name: "Micro thu âm không dây cài áo Shure Studio P15", category: "Thiết bị âm thanh & Hình ảnh", price: 879000, quantity: 80, stockQuantity: 80, minThreshold: 25, status: "IN_STOCK", supplierId: "sup-008", imageUrl: "", updatedAt: "2026-10-15T13:47:00.000Z" },
      { productId: "prod-0012", name: "Bộ dụng cụ sửa chữa đa năng Jogger 24 chi tiết", category: "Dụng cụ & Bảo hộ lao động", price: 358000, quantity: 0, stockQuantity: 0, minThreshold: 50, status: "OUT_OF_STOCK", supplierId: "sup-014", imageUrl: "", updatedAt: "2026-11-10T18:57:00.000Z" },
      // Thêm sản phẩm bổ sung từ data
      { productId: "prod-0013", name: "Màn hình máy tính Asus 34 inch UltraWide IPS 4K UHD 100Hz", category: "Máy tính & Laptop", price: 6290000, quantity: 40, stockQuantity: 40, minThreshold: 25, status: "IN_STOCK", supplierId: "sup-001", imageUrl: "", updatedAt: "2026-10-26T16:47:00.000Z" },
      { productId: "prod-0014", name: "Máy hủy tài liệu Xerox EB-E01", category: "Thiết bị văn phòng", price: 5960000, quantity: 6, stockQuantity: 6, minThreshold: 8, status: "IN_STOCK", supplierId: "sup-001", imageUrl: "", updatedAt: "2026-11-19T05:26:00.000Z" },
      { productId: "prod-0015", name: "Thanh RAM Desktop WD 16GB DDR5 5600MHz", category: "Linh kiện PC", price: 2830000, quantity: 109, stockQuantity: 109, minThreshold: 25, status: "IN_STOCK", supplierId: "sup-003", imageUrl: "", updatedAt: "2026-10-26T20:01:00.000Z" },
      { productId: "prod-0016", name: "Thùng cáp mạng MikroTik Cat5e UTP 305m", category: "Thiết bị mạng", price: 1720000, quantity: 45, stockQuantity: 45, minThreshold: 30, status: "IN_STOCK", supplierId: "sup-007", imageUrl: "", updatedAt: "2026-11-13T02:14:00.000Z" },
      { productId: "prod-0017", name: "Webcam hội nghị Full HD HyperX K8 Pro", category: "Phụ kiện công nghệ", price: 3060000, quantity: 19, stockQuantity: 19, minThreshold: 15, status: "IN_STOCK", supplierId: "sup-008", imageUrl: "", updatedAt: "2026-10-07T02:12:00.000Z" },
      { productId: "prod-0018", name: "Giấy in A4 Thiên Long định lượng 80gsm (Ram 500 tờ)", category: "Văn phòng phẩm", price: 89000, quantity: 106, stockQuantity: 106, minThreshold: 20, status: "IN_STOCK", supplierId: "sup-004", imageUrl: "", updatedAt: "2026-11-01T13:39:00.000Z" },
      { productId: "prod-0022", name: "Bộ lưu điện UPS Offline Sino 650VA/390W", category: "Thiết bị điện & Chiếu sáng", price: 2910000, quantity: 15, stockQuantity: 15, minThreshold: 5, status: "IN_STOCK", supplierId: "sup-014", imageUrl: "", updatedAt: "2026-10-22T03:07:00.000Z" },
      { productId: "prod-0970", name: "Bộ lưu điện UPS Offline Panasonic 650VA/390W", category: "Thiết bị điện & Chiếu sáng", price: 2910000, quantity: 125, stockQuantity: 125, minThreshold: 50, status: "IN_STOCK", supplierId: "sup-011", imageUrl: "", updatedAt: "2026-11-20T10:00:00.000Z" },
    ],

    transactions: [
      {
        transactionId: "txn-20261125-001",
        timestamp: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
        performedBy: "admin@cloudstock.local",
        type: "IN",
        productId: "prod-0003",
        productName: "Ổ cứng SSD Kingston 2TB M.2 NVMe PCIe Gen3",
        amount: 20,
        quantity: 20,
        supplierId: "sup-006",
        reason: "Nhập bổ sung linh kiện theo hợp đồng cung ứng số HD-FPT-Q4",
        invoiceKey: "invoices/HD_FPT_SSD_20261125.pdf",
        invoiceUrl: "s3://cloudstock-invoices/invoices/HD_FPT_SSD_20261125.pdf",
      },
      {
        transactionId: "txn-20261125-002",
        timestamp: new Date(Date.now() - 1000 * 60 * 60).toISOString(),
        performedBy: "staff@cloudstock.local",
        type: "OUT",
        productId: "prod-0018",
        productName: "Giấy in A4 Thiên Long định lượng 80gsm (Ram 500 tờ)",
        amount: 30,
        quantity: 30,
        supplierId: null,
        reason: "Xuất bán khách hàng - Đơn hàng bán sỉ doanh nghiệp #DH-9821",
        invoiceKey: null,
        invoiceUrl: "",
      },
      {
        transactionId: "txn-20261125-003",
        timestamp: new Date(Date.now() - 1000 * 60 * 60 * 3).toISOString(),
        performedBy: "admin@cloudstock.local",
        type: "IN",
        productId: "prod-0001",
        productName: "Màn hình máy tính LG 23.8 inch IPS 2K QHD 165Hz",
        amount: 30,
        quantity: 30,
        supplierId: "sup-001",
        reason: "Nhập lô màn hình trang bị cho phòng R&D Chi nhánh Đà Nẵng",
        invoiceKey: "invoices/BBGN_LG_Monitor_Lot44.pdf",
        invoiceUrl: "s3://cloudstock-invoices/invoices/BBGN_LG_Monitor_Lot44.pdf",
      },
      {
        transactionId: "txn-20261125-004",
        timestamp: new Date(Date.now() - 1000 * 60 * 60 * 5).toISOString(),
        performedBy: "staff@cloudstock.local",
        type: "OUT",
        productId: "prod-0004",
        productName: "Router cân bằng tải Ubiquiti EAP650",
        amount: 10,
        quantity: 10,
        supplierId: null,
        reason: "Xuất chuyển chi nhánh - Điều chuyển kho chi nhánh Hà Nội đợt 2",
        invoiceKey: null,
        invoiceUrl: "",
      },
      {
        transactionId: "txn-20261125-005",
        timestamp: new Date(Date.now() - 1000 * 60 * 60 * 8).toISOString(),
        performedBy: "admin@cloudstock.local",
        type: "IN",
        productId: "prod-0970",
        productName: "Bộ lưu điện UPS Offline Panasonic 650VA/390W",
        amount: 25,
        quantity: 25,
        supplierId: "sup-011",
        reason: "Nhập hàng định kỳ theo hợp đồng số 42",
        invoiceKey: null,
        invoiceUrl: "",
      },
      {
        transactionId: "txn-20261125-006",
        timestamp: new Date(Date.now() - 1000 * 60 * 60 * 12).toISOString(),
        performedBy: "staff@cloudstock.local",
        type: "OUT",
        productId: "prod-0005",
        productName: "Ổ cứng di động SSD gắn ngoài HyperX 1TB",
        amount: 5,
        quantity: 5,
        supplierId: null,
        reason: "Xuất hủy do hư hỏng/hết hạn - Lỗi chập mạch board nguồn trong kho",
        invoiceKey: null,
        invoiceUrl: "",
      },
      {
        transactionId: "txn-20261125-007",
        timestamp: new Date(Date.now() - 1000 * 60 * 60 * 20).toISOString(),
        performedBy: "admin@cloudstock.local",
        type: "IN",
        productId: "prod-0008",
        productName: "Camera IP Thân ngoài trời Hikvision 2MP Full HD hồng ngoại 30m",
        amount: 10,
        quantity: 10,
        supplierId: "sup-012",
        reason: "Nhập đợt camera an ninh cho dự án toà nhà VP mới",
        invoiceKey: "invoices/HoaDon_Camera_HikVision.pdf",
        invoiceUrl: "s3://cloudstock-invoices/invoices/HoaDon_Camera_HikVision.pdf",
      },
    ],

    users: [
      {
        id: "u-admin",
        username: "admin@cloudstock.local",
        fullName: "Quản trị viên Hệ thống",
        email: "admin@cloudstock.local",
        role: "Admin",
        status: "ACTIVE",
      },
      {
        id: "u-staff",
        username: "staff@cloudstock.local",
        fullName: "Nhân viên Kho",
        email: "staff@cloudstock.local",
        role: "Staff",
        status: "ACTIVE",
      },
      {
        id: "u-thukho",
        username: "thukho.nguyen",
        fullName: "Nguyễn Văn Hùng (Thủ kho chính)",
        email: "hung.nv@cloudstock.vn",
        role: "Staff",
        status: "ACTIVE",
      },
    ],

    systemLogs: [
      {
        timestamp: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
        logStream: "lambda/inventoryService",
        level: "INFO",
        message: "POST /transactions [IN] - Nhập kho thành công: +20 Ổ cứng SSD Kingston 2TB bởi admin@cloudstock.local",
      },
      {
        timestamp: new Date(Date.now() - 1000 * 60 * 60).toISOString(),
        logStream: "lambda/inventoryService",
        level: "INFO",
        message: "POST /transactions [OUT] - Xuất kho thành công: -30 Giấy in A4 Thiên Long 80gsm bởi staff@cloudstock.local",
      },
      {
        timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
        logStream: "lambda/alertService",
        level: "WARN",
        message: "CẢNH BÁO TỒN KHO: Sản phẩm prod-0002 (Máy in mã vạch Epson) giảm xuống còn 20 < ngưỡng tối thiểu (50). Lambda SNS: Đã phát cảnh báo tới Ban quản lý kho.",
      },
      {
        timestamp: new Date(Date.now() - 1000 * 60 * 60 * 3).toISOString(),
        logStream: "/aws/lambda/s3UploadPresignedUrl",
        level: "INFO",
        message: "S3 Event: s3:ObjectCreated:Put vào bucket 'cloudstock-invoices-ap-southeast-1' - Key: 'invoices/BBGN_LG_Monitor_Lot44.pdf' (size: 312KB) - Pre-signed URL verified.",
      },
      {
        timestamp: new Date(Date.now() - 1000 * 60 * 60 * 5).toISOString(),
        logStream: "/aws/lambda/processStockTransaction",
        level: "WARN",
        message: "SNS Publish: Topic 'arn:aws:sns:ap-southeast-1:123456789:InventoryLowStockAlert' được kích hoạt bởi DynamoDB Streams. Sản phẩm prod-0008 xuống dưới ngưỡng an toàn (4 < 5). Email đã gửi tới Ban Quản Lý.",
      },
      {
        timestamp: new Date(Date.now() - 1000 * 60 * 60 * 8).toISOString(),
        logStream: "/aws/lambda/inventoryService",
        level: "ERROR",
        message: "DynamoDB ConditionalCheckFailedException: Giao dịch xuất kho prod-0010 bị từ chối do tồn kho hiện tại = 0 (OUT_OF_STOCK). HTTP 409 Conflict.",
      },
      {
        timestamp: new Date(Date.now() - 1000 * 60 * 60 * 10).toISOString(),
        logStream: "lambda/inventoryService",
        level: "INFO",
        message: "GET /products - DynamoDB Scan thành công: 20 sản phẩm, 2 hết hàng (OUT_OF_STOCK), 3 dưới ngưỡng an toàn.",
      },
    ],
  };

  function _load(col) {
    const raw = localStorage.getItem(STORAGE_PREFIX + col);
    if (!raw) {
      const def = DEFAULT_DATA[col] || [];
      _save(col, def);
      return def;
    }
    try {
      return JSON.parse(raw);
    } catch {
      return DEFAULT_DATA[col] || [];
    }
  }

  function _save(col, data) {
    localStorage.setItem(STORAGE_PREFIX + col, JSON.stringify(data));
  }

  return {
    getAll(col) {
      return _load(col);
    },
    getById(col, idField, id) {
      const list = _load(col);
      return list.find((item) => String(item[idField]) === String(id)) || null;
    },
    add(col, record) {
      const list = _load(col);
      list.unshift(record);
      _save(col, list);
      return record;
    },
    update(col, idField, id, updates) {
      const list = _load(col);
      const idx = list.findIndex((item) => String(item[idField]) === String(id));
      if (idx === -1) return null;
      list[idx] = { ...list[idx], ...updates };
      _save(col, list);
      return list[idx];
    },
    remove(col, idField, id) {
      let list = _load(col);
      const beforeLen = list.length;
      list = list.filter((item) => String(item[idField]) !== String(id));
      _save(col, list);
      return list.length < beforeLen;
    },
    reset() {
      Object.keys(DEFAULT_DATA).forEach((col) => {
        _save(col, JSON.parse(JSON.stringify(DEFAULT_DATA[col])));
      });
      return true;
    },
  };
})();

// Tự động khởi tạo dữ liệu ban đầu nếu localStorage chưa có
(function initDefaultStorage() {
  if (typeof window !== "undefined" && window.localStorage) {
    if (!localStorage.getItem("cloudstock_mock_products")) {
      MockDataStore.reset();
    }
  }
})();
