"""DaySupply — deployment skeleton (Block 1)."""

import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="DaySupply", version="0.1.0")


@app.get("/healthz")
async def healthz():
    """Liveness probe for Cloud Run."""
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def root():
    """Placeholder landing page — replaced in later blocks."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DaySupply</title>
  <style>
    body {
      margin: 0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: system-ui, -apple-system, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
    }
    .container {
      text-align: center;
    }
    h1 {
      font-size: 3rem;
      margin-bottom: 0.25rem;
    }
    p {
      color: #94a3b8;
      font-size: 1.1rem;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>DaySupply</h1>
    <p>Voice-first medicine stock reporting &amp; redistribution</p>
  </div>
</body>
</html>"""
