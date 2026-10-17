"""Phone link dashboard: sign in on the laptop, link a phone with a QR code, record on the phone, check on the laptop.

Run:  python -m backend.dashboard        then open http://localhost:8700

One process, two servers:
- the dashboard (create account, sign in, QR code, results) on http://localhost only, so nobody else on the
  Wi-Fi can reach the accounts;
- the phone pages (pair, record or upload, send) on https://<laptop Wi-Fi address>, because phone browsers
  only allow the microphone over HTTPS. The certificate is self-signed, so the phone warns once.

A QR code carries a one-time pairing token that expires after settings.PAIRING_TTL_S. Audio is checked in memory
and discarded; only the result is stored, and the result of every check is emailed to its owner.
"""
