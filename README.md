# CloudStock - He thong Quan ly Kho Serverless tren AWS

He thong Quan ly Kho (Inventory Management System) kien truc Serverless hien dai duoc xay dung tren nen tang dien toan dam may Amazon Web Services (AWS).

---

## 1. Kien truc He thong (AWS Architecture)

- **Frontend Hosting**: Amazon S3 (Static Website Hosting) ket hop Amazon CloudFront (CDN phan phoi toan cau).
- **Authentication & Directory**: Amazon Cognito User Pools (Xac thuc nguoi dung, phan quyen Admin / Staff).
- **API Gateway**: Amazon API Gateway (RESTful API, xac thuc qua Bearer JWT Token).
- **Backend Compute**: AWS Lambda (Python Runtime) xu ly logic nghiep vu inventory, bao cao, canh bao.
- **Database**: Amazon DynamoDB (NoSQL toc do cao luu tru Products, Suppliers, Transactions).
- **Object Storage**: Amazon S3 Buckets (Luu tru hoa don, chung tu nhap xuat va anh san pham qua Pre-signed URL).
- **Monitoring & Alerting**: Amazon CloudWatch Logs & Amazon SNS (Gui email canh bao ton kho toi thieu).

---

## 2. Cau truc Thu muc

```
CloudStock/
├── .gitignore               # Loai bo file rac he dieu hanh, IDE va moi truong Python
├── README.md                # Tai lieu huong dan du an
├── backend/                 # Ma nguon backend AWS Lambda (Python)
│   └── .gitkeep
└── frontend/                # Toan bo giao dien nguoi dung (HTML5, CSS3, Vanilla JS)
    ├── css/
    │   └── style.css        # He thong thiet ke Swiss / Corporate Minimalist
    ├── js/
    │   ├── config.js        # Cau hinh tap trung (USE_MOCK_DATA, API Gateway URL, Cognito)
    │   ├── mock-data.js     # Du lieu mau sat thuc te + dong bo localStorage
    │   ├── api.js           # ApiService - Lop trung gian giao tiep JSON
    │   ├── app.js           # Router & Application Controller (Dieu phoi chuyen tab SPA)
    │   ├── auth.js          # Module 1 & 6: Xac thuc Cognito & Quan ly Nguoi dung Doc lap
    │   ├── dashboard.js     # Module 2: Tong quan Dashboard (Chart.js & Canh bao ton)
    │   ├── products.js      # Module 3A: Quan ly Danh muc Hang hoa (DynamoDB + S3 Upload)
    │   ├── suppliers.js     # Module 3B: Quan ly Danh sach Nha cung cap
    │   ├── inventory.js     # Module 4: Nghiep vu Kho (Nhap kho & Xuat kho an toan)
    │   └── reports.js       # Module 5: Lich su Giao dich (Excel/PDF) & CloudWatch Logs
    ├── index.html           # Ung dung Single Page Application (SPA) chinh
    └── login.html           # Man hinh Dang nhap xac thuc
```

---

## 3. Huong dan Chay thu Giao dien (Quick Start)

Frontend duoc viet bang HTML5, CSS3 va JavaScript (ES6+) thuan tuy, khong can cai dat Node.js, npm hay bat ky trinh bien dich nao.

1. Mo truc tiep file `frontend/login.html` tren trinh duyet (Chrome, Firefox, Safari, Edge) hoac su dung tien ich Live Server / Python HTTP Server:
   ```bash
   cd frontend
   python3 -m http.server 8080
   ```
2. Truy cap dia chi: `http://localhost:8080/login.html`

### Tai khoan Demo san co:
| Username | Mat khau | Vai tro | Trang thai | Ghi chu |
|---|---|---|---|---|
| `admin.nguyen` | 1 | Admin | ACTIVE | Toan quyen he thong + Quan ly nguoi dung |
| `staff.tran` | 1 | Staff | ACTIVE | Thu kho (Thuc hien Nhap/Xuat hang) |
| `staff.pham` | 1 | Staff | LOCKED | Demo tai khoan bi quan tri vien khoa |

---

## 4. Chuyen doi sang Backend AWS that

Khi nhom Backend hoan thien ha tang tren AWS SAM / Terraform, chi can mo file `frontend/js/config.js` va thay doi:

```javascript
const CONFIG = Object.freeze({
  USE_MOCK_DATA: false, // Chuyen thanh false de goi API that
  API_BASE_URL: "https://<your-api-id>.execute-api.ap-southeast-1.amazonaws.com/prod",
  COGNITO_USER_POOL_ID: "ap-southeast-1_XXXXXXXXX",
  COGNITO_CLIENT_ID: "xxxxxxxxxxxxxxxxxxxxxxxxxx",
  ...
});
```

---

## 5. Quy chuan Thiet ke (Design Principles)

- **Phong cach Swiss / Corporate Minimalist**: Tap trung vao Typography ro rang, bang du lieu truc quan, the thong ke tuong phan nhe.
- **Khong bieu tuong (Zero Icons, Zero SVG, Zero Emoji)**: Dung hoan toan Text Badges, mau sac ngu nghia va khoang trang theo chuan doanh nghiep.

