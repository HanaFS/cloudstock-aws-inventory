const CONFIG = Object.freeze({
  USE_MOCK_DATA: true,
  USE_MOCK_AUTH: true,
  USE_LOCAL_API: true,
  USE_LOCAL_API_AUTH: true,

  API_BASE_URL: "http://127.0.0.1:3001",

  COGNITO_USER_POOL_ID: "",
  COGNITO_CLIENT_ID: "",
  COGNITO_HOSTED_UI_DOMAIN: "",
  COGNITO_REDIRECT_URI: "http://localhost:8080/login.html",
  COGNITO_LOGOUT_URI: "http://localhost:8080/login.html",
  COGNITO_SCOPES: ["openid", "email", "profile"],

  APP_NAME: "CloudStock",
  PAGE_SIZE: 10,
  MOCK_DELAY_MS: 200,
});

