"use strict";

const fastify = require("fastify")({
  logger: true,
});

const region = process.env.REGION_NAME || process.env.REGION || "unknown";
const port = Number(process.env.PORT || 3001);

fastify.get("/health", async () => {
  return {
    ok: true,
    region,
    now: new Date().toISOString(),
  };
});

fastify.post("/handle", async (request) => {
  const body = request.body || {};
  return {
    ok: true,
    region,
    clientId: body.clientId || null,
    echo: body.payload || null,
    handledAt: new Date().toISOString(),
  };
});

const start = async () => {
  try {
    await fastify.listen({ port, host: "0.0.0.0" });
    fastify.log.info(`Backend ${region} listening on ${port}`);
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
};

start();
