exports.handler = async () => ({
  statusCode: 200,
  headers: {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": process.env.FRONTEND_ORIGIN || "http://localhost:8080",
    "Vary": "Origin",
  },
  body: JSON.stringify({
    success: true,
    data: {
      service: "cloudstock-api",
      status: "ok",
      stage: process.env.STAGE || "dev",
    },
  }),
});
