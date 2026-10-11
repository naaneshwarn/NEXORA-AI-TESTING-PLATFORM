import express from 'express';

const app = express();
const port = Number(process.env.PORT ?? 4000);

app.use(express.json());

app.get('/health', (_req, res) => {
  res.json({
    status: 'ok',
    service: 'nexora-api',
    timestamp: new Date().toISOString()
  });
});

app.get('/api/status', (_req, res) => {
  res.json({
    app: 'NEXORA',
    environment: process.env.NODE_ENV ?? 'development',
    ready: true
  });
});

app.listen(port, () => {
  console.log(`NEXORA API listening on http://localhost:${port}`);
});
