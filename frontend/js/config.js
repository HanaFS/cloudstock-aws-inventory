// File: frontend/js/config.js
const AWS_CONFIG = {
  REGION: 'ap-southeast-1',
  API_BASE_URL: 'https://8od8y28vg9.execute-api.ap-southeast-1.amazonaws.com',
  COGNITO: {
    USER_POOL_ID: 'ap-southeast-1_OnVjalo1T',
    CLIENT_ID: '7qmk3hnllp292nguotfht8m7uh',
    GROUPS: {
      ADMIN: 'Admin',
      STAFF: 'Staff'
    }
  },
  S3: {
    BUCKET_NAME: 'qlkho-assets-nhom4-2026',
    PUBLIC_PRODUCT_PREFIX: 'products/',
    PRIVATE_INVOICE_PREFIX: 'invoices/',
    PUBLIC_BASE_URL: 'https://qlkho-assets-nhom4-2026.s3.ap-southeast-1.amazonaws.com'
  },
  ENUMS: {
    PRODUCT_STATUS: { IN_STOCK: 'IN_STOCK', OUT_OF_STOCK: 'OUT_OF_STOCK' },
    TRANSACTION_TYPE: { IMPORT: 'IMPORT', EXPORT: 'EXPORT' }
  }
};

// Hàm helper gọi API tự động đính kèm Header Authorization: Bearer <id_token>
async function apiRequest(path, options = {}) {
  const idToken = localStorage.getItem('id_token') || localStorage.getItem('cloudstock_id_token');
  const headers = {
    'Content-Type': 'application/json',
    ...(idToken ? { 'Authorization': `Bearer ${idToken}` } : {}),
    ...(options.headers || {})
  };
  const response = await fetch(`${AWS_CONFIG.API_BASE_URL}${path}`, { ...options, headers });
  const data = await response.json();
  if (!response.ok) throw new Error(data.message || 'Lỗi gọi API');
  return data;
}

const CONFIG = Object.freeze({
  USE_MOCK_DATA: true, 
  USE_MOCK_AUTH: true,  
  USE_LOCAL_API: true,  
  USE_LOCAL_API_AUTH: true,

  API_BASE_URL: "http://localhost:3001",

  COGNITO_USER_POOL_ID: AWS_CONFIG.COGNITO.USER_POOL_ID,
  COGNITO_CLIENT_ID: AWS_CONFIG.COGNITO.CLIENT_ID,
  COGNITO_HOSTED_UI_DOMAIN: "",
  COGNITO_REDIRECT_URI: (typeof window !== "undefined" ? window.location.origin : "http://localhost:8080") + "/login.html",
  COGNITO_LOGOUT_URI: (typeof window !== "undefined" ? window.location.origin : "http://localhost:8080") + "/login.html",
  COGNITO_SCOPES: ["openid", "email", "profile"],

  APP_NAME: "CloudStock",
  PAGE_SIZE: 50,
  MOCK_DELAY_MS: 0,
});
