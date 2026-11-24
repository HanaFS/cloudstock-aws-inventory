// // File: frontend/js/mockData.js
// // Bộ dữ liệu mẫu phong phú dành riêng cho Nghiệp vụ Kho (Inventory Operations), Sản phẩm, NCC & Báo cáo

// const MockDataStore = (() => {
//   const STORAGE_PREFIX = "cloudstock_mock_";

//   const DEFAULT_DATA = {
//     suppliers: [
//       {
//         supplierId: "sup-001",
//         name: "Công ty TNHH Phân Phối Công Nghệ FPT Synnex",
//         phone: "02873006688",
//         address: "Lô T2-1.2 Đường D1, Khu Công Nghệ Cao, TP. Thủ Đức, TP.HCM",
//       },
//       {
//         supplierId: "sup-002",
//         name: "Công ty CP Thế Giới Số Digiworld",
//         phone: "02839290059",
//         address: "Số 195-197 Nguyễn Thái Bình, Phường Nguyễn Thái Bình, Quận 1, TP.HCM",
//       },
//       {
//         supplierId: "sup-003",
//         name: "Công ty TNHH Tin Học Viễn Thông Viễn Sơn",
//         phone: "02838326085",
//         address: "Số 162 Bùi Thị Xuân, Phường Phạm Ngũ Lão, Quận 1, TP.HCM",
//       },
//       {
//         supplierId: "sup-004",
//         name: "Công ty CP Tập Đoàn Thiên Long",
//         phone: "02837505555",
//         address: "Lô 6-8-10 Đường số 3, KCN Tân Tạo, Quận Bình Tân, TP.HCM",
//       },
//       {
//         supplierId: "sup-005",
//         name: "Công ty TNHH Thiết Bị Văn Phòng Lê Bảo Minh (Canon VN)",
//         phone: "02838330777",
//         address: "Số 184 Nam Kỳ Khởi Nghĩa, Phường Võ Thị Sáu, Quận 3, TP.HCM",
//       },
//       {
//         supplierId: "sup-006",
//         name: "Công ty CP Bóng Đèn Phích Nước Rạng Đông",
//         phone: "02438584310",
//         address: "Số 87-89 Phố Hạ Đình, Phường Thanh Xuân Trung, Quận Thanh Xuân, Hà Nội",
//       },
//     ],

//     products: [
//       {
//         productId: "prod-0001",
//         name: "Màn hình máy tính LG UltraGear 24 inch 2K IPS 165Hz",
//         category: "Máy tính & Laptop",
//         price: 4180000,
//         quantity: 45,
//         stockQuantity: 45,
//         minThreshold: 20,
//         status: "IN_STOCK",
//         supplierId: "sup-001",
//         imageUrl: "",
//         updatedAt: new Date(Date.now() - 3600000 * 4).toISOString(),
//       },
//       {
//         productId: "prod-0002",
//         name: "Máy in mã vạch tem nhãn nhiệt Epson HL-L2321D",
//         category: "Thiết bị văn phòng",
//         price: 4870000,
//         quantity: 8,
//         stockQuantity: 8,
//         minThreshold: 15,
//         status: "IN_STOCK", // DƯỚI NGƯỠNG: 8 < 15
//         supplierId: "sup-005",
//         imageUrl: "",
//         updatedAt: new Date(Date.now() - 3600000 * 8).toISOString(),
//       },
//       {
//         productId: "prod-0003",
//         name: "Bút bi gel Thiên Long 0.5mm xanh (Hộp 20 cây)",
//         category: "Văn phòng phẩm",
//         price: 120000,
//         quantity: 1250,
//         stockQuantity: 1250,
//         minThreshold: 200,
//         status: "IN_STOCK",
//         supplierId: "sup-004",
//         imageUrl: "",
//         updatedAt: new Date(Date.now() - 3600000 * 2).toISOString(),
//       },
//       {
//         productId: "prod-0004",
//         name: "Giấy in A4 Double A 70gsm (Ram 500 tờ)",
//         category: "Văn phòng phẩm",
//         price: 85000,
//         quantity: 18,
//         stockQuantity: 18,
//         minThreshold: 50,
//         status: "IN_STOCK", // DƯỚI NGƯỠNG: 18 < 50
//         supplierId: "sup-004",
//         imageUrl: "",
//         updatedAt: new Date(Date.now() - 3600000 * 5).toISOString(),
//       },
//       {
//         productId: "prod-0005",
//         name: "Bàn phím cơ không dây Logitech G Pro Wireless",
//         category: "Phụ kiện công nghệ",
//         price: 2150000,
//         quantity: 14,
//         stockQuantity: 14,
//         minThreshold: 10,
//         status: "IN_STOCK",
//         supplierId: "sup-002",
//         imageUrl: "",
//         updatedAt: new Date(Date.now() - 3600000 * 24).toISOString(),
//       },
//       {
//         productId: "prod-0006",
//         name: "Chuột quang văn phòng có dây Logitech B100 USB",
//         category: "Phụ kiện công nghệ",
//         price: 95000,
//         quantity: 120,
//         stockQuantity: 120,
//         minThreshold: 30,
//         status: "IN_STOCK",
//         supplierId: "sup-002",
//         imageUrl: "",
//         updatedAt: new Date(Date.now() - 3600000 * 12).toISOString(),
//       },
//       {
//         productId: "prod-0007",
//         name: "Router định tuyến doanh nghiệp Cisco RV340 Dual WAN Gigabit",
//         category: "Thiết bị mạng",
//         price: 6850000,
//         quantity: 4,
//         stockQuantity: 4,
//         minThreshold: 5,
//         status: "IN_STOCK", // DƯỚI NGƯỠNG: 4 < 5
//         supplierId: "sup-003",
//         imageUrl: "",
//         updatedAt: new Date(Date.now() - 3600000 * 18).toISOString(),
//       },
//       {
//         productId: "prod-0008",
//         name: "Ổ cứng thể rắn SSD Samsung 980 PRO 1TB PCIe NVMe M.2",
//         category: "Linh kiện PC",
//         price: 2490000,
//         quantity: 35,
//         stockQuantity: 35,
//         minThreshold: 15,
//         status: "IN_STOCK",
//         supplierId: "sup-001",
//         imageUrl: "",
//         updatedAt: new Date(Date.now() - 3600000 * 1).toISOString(),
//       },
//       {
//         productId: "prod-0009",
//         name: "Máy quét tài liệu để bàn Canon imageFORMULA DR-C225 II",
//         category: "Thiết bị văn phòng",
//         price: 8900000,
//         quantity: 2,
//         stockQuantity: 2,
//         minThreshold: 5,
//         status: "IN_STOCK", // DƯỚI NGƯỠNG: 2 < 5
//         supplierId: "sup-005",
//         imageUrl: "",
//         updatedAt: new Date(Date.now() - 3600000 * 28).toISOString(),
//       },
//       {
//         productId: "prod-0010",
//         name: "Switch mạng chia cổng TP-Link 24 Port Gigabit SG1024D",
//         category: "Thiết bị mạng",
//         price: 1650000,
//         quantity: 28,
//         stockQuantity: 28,
//         minThreshold: 10,
//         status: "IN_STOCK",
//         supplierId: "sup-003",
//         imageUrl: "",
//         updatedAt: new Date(Date.now() - 3600000 * 30).toISOString(),
//       },
//       {
//         productId: "prod-0011",
//         name: "Bộ lưu điện dự phòng UPS APC Back-UPS 650VA BX650LI-MS",
//         category: "Thiết bị điện & Chiếu sáng",
//         price: 1350000,
//         quantity: 0,
//         stockQuantity: 0,
//         minThreshold: 8,
//         status: "OUT_OF_STOCK", // HẾT HÀNG (Tồn 0)
//         supplierId: "sup-001",
//         imageUrl: "",
//         updatedAt: new Date(Date.now() - 3600000 * 48).toISOString(),
//       },
//       {
//         productId: "prod-0012",
//         name: "Camera IP thân trụ chống nước Hikvision 2MP hồng ngoại 30m",
//         category: "Thiết bị an ninh & Camera",
//         price: 950000,
//         quantity: 60,
//         stockQuantity: 60,
//         minThreshold: 20,
//         status: "IN_STOCK",
//         supplierId: "sup-003",
//         imageUrl: "",
//         updatedAt: new Date(Date.now() - 3600000 * 15).toISOString(),
//       },
//     ],

//     transactions: [
//       {
//         transactionId: "txn-20261124-001",
//         timestamp: new Date(Date.now() - 1000 * 60 * 15).toISOString(), // 15 phút trước
//         performedBy: "thukho.nguyen",
//         type: "IN",
//         productId: "prod-0008",
//         productName: "Ổ cứng thể rắn SSD Samsung 980 PRO 1TB PCIe NVMe M.2",
//         amount: 20,
//         quantity: 20,
//         supplierId: "sup-001",
//         reason: "Nhập bổ sung linh kiện theo hợp đồng cung ứng số HD-FPT-Q4",
//         invoiceKey: "invoices/HD_FPT_SSD_20261124.pdf",
//         invoiceUrl: "s3://cloudstock-invoices-ap-southeast-1/invoices/HD_FPT_SSD_20261124.pdf",
//       },
//       {
//         transactionId: "txn-20261124-002",
//         timestamp: new Date(Date.now() - 1000 * 60 * 60).toISOString(), // 1 giờ trước
//         performedBy: "staff.tran",
//         type: "OUT",
//         productId: "prod-0003",
//         productName: "Bút bi gel Thiên Long 0.5mm xanh (Hộp 20 cây)",
//         amount: 150,
//         quantity: 150,
//         supplierId: null,
//         reason: "Xuất bán khách hàng - Đơn hàng bán sỉ doanh nghiệp #DH-9821",
//         invoiceKey: null,
//         invoiceUrl: "",
//       },
//       {
//         transactionId: "txn-20261124-003",
//         timestamp: new Date(Date.now() - 1000 * 60 * 60 * 3).toISOString(), // 3 giờ trước
//         performedBy: "admin",
//         type: "IN",
//         productId: "prod-0001",
//         productName: "Màn hình máy tính LG UltraGear 24 inch 2K IPS 165Hz",
//         amount: 30,
//         quantity: 30,
//         supplierId: "sup-001",
//         reason: "Nhập lô màn hình trang bị cho phòng R&D Chi nhánh Đà Nẵng",
//         invoiceKey: "invoices/BBGN_LG_Monitor_Lot44.pdf",
//         invoiceUrl: "s3://cloudstock-invoices-ap-southeast-1/invoices/BBGN_LG_Monitor_Lot44.pdf",
//       },
//       {
//         transactionId: "txn-20261124-004",
//         timestamp: new Date(Date.now() - 1000 * 60 * 60 * 5).toISOString(), // 5 giờ trước
//         performedBy: "thukho.nguyen",
//         type: "OUT",
//         productId: "prod-0004",
//         productName: "Giấy in A4 Double A 70gsm (Ram 500 tờ)",
//         amount: 50,
//         quantity: 50,
//         supplierId: null,
//         reason: "Xuất chuyển chi nhánh - Điều chuyển kho chi nhánh Hà Nội đợt 2",
//         invoiceKey: null,
//         invoiceUrl: "",
//       },
//       {
//         transactionId: "txn-20261124-005",
//         timestamp: new Date(Date.now() - 1000 * 60 * 60 * 8).toISOString(), // 8 giờ trước
//         performedBy: "staff.tran",
//         type: "OUT",
//         productId: "prod-0002",
//         productName: "Máy in mã vạch tem nhãn nhiệt Epson HL-L2321D",
//         amount: 5,
//         quantity: 5,
//         supplierId: null,
//         reason: "Xuất bán khách hàng - Bàn giao cho Công ty Cổ phần Vận Tải Á Châu",
//         invoiceKey: null,
//         invoiceUrl: "",
//       },
//       {
//         transactionId: "txn-20261124-006",
//         timestamp: new Date(Date.now() - 1000 * 60 * 60 * 22).toISOString(), // 22 giờ trước
//         performedBy: "thukho.nguyen",
//         type: "IN",
//         productId: "prod-0010",
//         productName: "Switch mạng chia cổng TP-Link 24 Port Gigabit SG1024D",
//         amount: 15,
//         quantity: 15,
//         supplierId: "sup-003",
//         reason: "Nhập đợt thiết bị mạng định kỳ tuần 4 tháng 11 từ Viễn Sơn",
//         invoiceKey: "invoices/HoaDon_VienSon_Network2026.pdf",
//         invoiceUrl: "s3://cloudstock-invoices-ap-southeast-1/invoices/HoaDon_VienSon_Network2026.pdf",
//       },
//       {
//         transactionId: "txn-20261124-007",
//         timestamp: new Date(Date.now() - 1000 * 60 * 60 * 26).toISOString(), // 26 giờ trước
//         performedBy: "admin",
//         type: "OUT",
//         productId: "prod-0005",
//         productName: "Bàn phím cơ không dây Logitech G Pro Wireless",
//         amount: 2,
//         quantity: 2,
//         supplierId: null,
//         reason: "Xuất hủy do hư hỏng/hết hạn - Lỗi chập mạch board nguồn trong kho",
//         invoiceKey: null,
//         invoiceUrl: "",
//       },
//     ],

//     users: [
//       {
//         id: "u-admin",
//         username: "admin",
//         fullName: "Quản trị viên Hệ thống",
//         email: "admin@cloudstock.vn",
//         role: "Admin",
//         status: "ACTIVE",
//       },
//       {
//         id: "u-staff",
//         username: "staff",
//         fullName: "Nhân viên Kho",
//         email: "staff@cloudstock.vn",
//         role: "Staff",
//         status: "ACTIVE",
//       },
//       {
//         id: "u-thukho",
//         username: "thukho.nguyen",
//         fullName: "Nguyễn Văn Hùng (Thủ kho chính)",
//         email: "hung.nv@cloudstock.vn",
//         role: "Staff",
//         status: "ACTIVE",
//       },
//     ],

//     systemLogs: [
//       {
//         timestamp: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
//         logStream: "lambda/inventoryService",
//         level: "INFO",
//         message: "POST /transactions [IN] - Nhập kho thành công: +20 SSD Samsung 980 PRO 1TB bởi thukho.nguyen",
//       },
//       {
//         timestamp: new Date(Date.now() - 1000 * 60 * 60 * 5).toISOString(),
//         logStream: "lambda/alertService",
//         level: "WARN",
//         message: "CẢNH BÁO TỒN KHO: Giấy in A4 Double A giảm xuống còn 18 < ngưỡng tối thiểu (50). Đã gửi cảnh báo SNS.",
//       },
//     ],
//   };

//   function _load(col) {
//     const raw = localStorage.getItem(STORAGE_PREFIX + col);
//     if (!raw) {
//       const def = DEFAULT_DATA[col] || [];
//       _save(col, def);
//       return def;
//     }
//     try {
//       return JSON.parse(raw);
//     } catch {
//       return DEFAULT_DATA[col] || [];
//     }
//   }

//   function _save(col, data) {
//     localStorage.setItem(STORAGE_PREFIX + col, JSON.stringify(data));
//   }

//   return {
//     getAll(col) {
//       return _load(col);
//     },
//     getById(col, idField, id) {
//       const list = _load(col);
//       return list.find((item) => String(item[idField]) === String(id)) || null;
//     },
//     add(col, record) {
//       const list = _load(col);
//       list.unshift(record);
//       _save(col, list);
//       return record;
//     },
//     update(col, idField, id, updates) {
//       const list = _load(col);
//       const idx = list.findIndex((item) => String(item[idField]) === String(id));
//       if (idx === -1) return null;
//       list[idx] = { ...list[idx], ...updates };
//       _save(col, list);
//       return list[idx];
//     },
//     remove(col, idField, id) {
//       let list = _load(col);
//       const beforeLen = list.length;
//       list = list.filter((item) => String(item[idField]) !== String(id));
//       _save(col, list);
//       return list.length < beforeLen;
//     },
//     reset() {
//       Object.keys(DEFAULT_DATA).forEach((col) => {
//         _save(col, JSON.parse(JSON.stringify(DEFAULT_DATA[col])));
//       });
//       return true;
//     },
//   };
// })();

// // Tự động khởi tạo dữ liệu ban đầu nếu localStorage chưa có
// (function initDefaultStorage() {
//   if (typeof window !== "undefined" && window.localStorage) {
//     if (!localStorage.getItem("cloudstock_mock_products")) {
//       MockDataStore.reset();
//     }
//   }
// })();
