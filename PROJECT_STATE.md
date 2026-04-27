# WhatsApp Bot — Project State

## Implemented (code)
- `GET /healthz` — Render health check
- `GET /webhook` — Meta verify handshake (`hub.mode`, `hub.verify_token`, `hub.challenge`)
- `POST /webhook` — inbound messages; emergency keywords; payment flow; outbound replies via Cloud API when `WHATSAPP_TOKEN` + `WHATSAPP_PHONE_NUMBER_ID` set
- Payment: screenshot or image → reference ID → pending manual verification → approve/reject
- `POST /payment/approve`, `/payment/reject` — optional `ADMIN_API_KEY` via header `X-Admin-Key`
- `GET /payment/state/{sender}`, `GET /payment/states` — admin-protected when `ADMIN_API_KEY` set
- Doctor alert via WhatsApp to `DOCTOR_ALERT_NUMBER` when tokens configured

## You complete (dashboard)
1. **Render**: New Web Service → repo `wasifmalik-max/drwasif-whatsapp-bot` → copy env from `.env.example`
2. **Meta**: WhatsApp → Configuration → Webhook URL `https://<render-host>/webhook`, Verify Token = `WHATSAPP_VERIFY_TOKEN`
3. **GitHub**: Add secrets only if you automate beyond Render (optional)

## Resume
`Resume WhatsApp bot from PROJECT_STATE.md — continue deployment or next feature.`
