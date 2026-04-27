# Dr Wasif WhatsApp Bot (Ultra Minimal)

Production-minimal WhatsApp clinical assistant scaffold.

## Stack
- FastAPI (Python 3.11)
- Render deployment (`render.yaml`)
- GitHub Actions one-click deploy workflow

## Runtime Policy
- Claude is primary patient-facing model.
- Emergency messages escalate immediately.
- Payments require screenshot + transaction reference + manual doctor verification.

## Quick Start
1. Create GitHub repo and push this folder.
2. Connect repo to Render.
3. Set env vars from `.env.example`.
4. Use GitHub Actions `Deploy Bot` workflow for one-click deploy.

## Health Check
- `GET /healthz` -> `{ "ok": true }`

