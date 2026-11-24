const DEPLOY_OUTPUTS = {
  API_BASE_URL: "https://1mj1230a5d.execute-api.ap-southeast-1.amazonaws.com/dev",                 
  USER_POOL_ID: "ap-southeast-1_yvqtdZ5Tb",                         
  USER_POOL_CLIENT_ID: "3a6f7hfuflr5rhi7bqhnqo3gc7",    
  COGNITO_DOMAIN: "https://cloudstock-nhom4-202600.auth.ap-southeast-1.amazoncognito.com",    
  ASSETS_BUCKET: "cloudstock-assets-dev-925268418306-ap-southeast-1"   
};

const IS_LOCAL_DEVELOPMENT =
  typeof window !== "undefined" &&
  ["localhost", "127.0.0.1"].includes(window.location.hostname);

const AWS_CONFIG = {
  REGION: 'ap-southeast-1',
  API_BASE_URL: IS_LOCAL_DEVELOPMENT
    ? 'http://localhost:3001'
    : DEPLOY_OUTPUTS.API_BASE_URL,
  COGNITO: {
    USER_POOL_ID: DEPLOY_OUTPUTS.USER_POOL_ID,
    CLIENT_ID: DEPLOY_OUTPUTS.USER_POOL_CLIENT_ID,
    GROUPS: {
      ADMIN: 'Admin',
      STAFF: 'Staff'
    }
  },
  S3: {
    BUCKET_NAME: DEPLOY_OUTPUTS.ASSETS_BUCKET,
    PUBLIC_PRODUCT_PREFIX: 'products/',
    PRIVATE_INVOICE_PREFIX: 'invoices/',
    PUBLIC_BASE_URL: `https://${DEPLOY_OUTPUTS.ASSETS_BUCKET}.s3.ap-southeast-1.amazonaws.com`
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
  USE_MOCK_DATA: false,
  USE_MOCK_AUTH: false,
  USE_LOCAL_API: IS_LOCAL_DEVELOPMENT,
  USE_LOCAL_API_AUTH: IS_LOCAL_DEVELOPMENT,

  API_BASE_URL: AWS_CONFIG.API_BASE_URL,

  COGNITO_USER_POOL_ID: AWS_CONFIG.COGNITO.USER_POOL_ID,
  COGNITO_CLIENT_ID: AWS_CONFIG.COGNITO.CLIENT_ID,
  COGNITO_HOSTED_UI_DOMAIN: DEPLOY_OUTPUTS.COGNITO_DOMAIN,
  COGNITO_REDIRECT_URI: (typeof window !== "undefined" ? window.location.origin : "https://d7omav63h53i1.cloudfront.net") + "/login.html",
  COGNITO_LOGOUT_URI: (typeof window !== "undefined" ? window.location.origin : "https://d7omav63h53i1.cloudfront.net") + "/login.html",
  COGNITO_SCOPES: ["openid", "email", "profile"],

  APP_NAME: "CloudStock",
  PAGE_SIZE: 50,
  MOCK_DELAY_MS: 0,
});