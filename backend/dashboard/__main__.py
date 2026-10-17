"""Start the dashboard and the phone pages:  python -m backend.dashboard [--ip ADDRESS] [--no-browser]"""
import argparse
import logging
import threading
import time
import urllib.error
import urllib.request
import webbrowser

import uvicorn

from backend import settings
from backend.dashboard import checks, db, network, notify, server


def frontend_running():
    """True if the Next.js app answers, so the browser isn't opened on an error page."""
    try:
        urllib.request.urlopen(settings.FRONTEND_URL, timeout=2)
        return True
    except urllib.error.HTTPError:
        return True  # it answered, just not with 200
    except OSError:
        return False


def main():
    parser = argparse.ArgumentParser(description="VoiceDrift dashboard with phone link (same Wi-Fi).")
    parser.add_argument("--ip", help="the laptop address the QR code should use, if the detected one is wrong")
    parser.add_argument("--no-browser", action="store_true", help="don't open the dashboard in the browser")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("dashboard").setLevel(logging.INFO)  # linked phones and checks; not the models' chatter

    addresses = network.lan_addresses()
    if args.ip:
        addresses = [args.ip, *(a for a in addresses if a != args.ip)]
    cert, key = network.ensure_certificate(addresses)
    db.init()
    checks.start()

    quiet = {"log_level": "warning", "access_log": False}
    phone = uvicorn.Server(uvicorn.Config(server.phone_app(addresses), host="0.0.0.0", port=settings.PHONE_PORT,
                                          ssl_certfile=str(cert), ssl_keyfile=str(key), **quiet))
    laptop = uvicorn.Server(uvicorn.Config(server.laptop_app(addresses), host="127.0.0.1",
                                           port=settings.DASHBOARD_PORT, **quiet))
    phone_thread = threading.Thread(target=phone.run, name="phone-server", daemon=True)
    phone_thread.start()  # signals stay with the main thread, so Ctrl+C stops the dashboard, then this
    while not phone.started and phone_thread.is_alive():
        time.sleep(0.05)
    if not phone.started:
        raise SystemExit(f"Couldn't start the phone pages on port {settings.PHONE_PORT}: is VoiceDrift already running?")

    smtp = notify.smtp_settings()
    print(f"\nVoiceDrift backend with phone link\n"
          f"  Web app (Next.js):          {settings.FRONTEND_URL}   start it with: cd frontend && npm run dev\n"
          f"  API, on this laptop:        http://localhost:{settings.DASHBOARD_PORT}/api\n"
          f"  Phone pages, same Wi-Fi:    https://{addresses[0]}:{settings.PHONE_PORT}"
          + (f"   (also: {', '.join(addresses[1:])})" if len(addresses) > 1 else "") + "\n"
          f"  Database: {db.safe_url()}\n"
          f"  Email: {'via ' + smtp['host'] if smtp else f'not set up, notifications are saved in {settings.OUTBOX_DIR}'}\n"
          f"If the phone can't open the page: allow Python through Windows Firewall on private networks and\n"
          f"check that both devices are on the same Wi-Fi (not a guest network). Ctrl+C stops VoiceDrift.\n",
          flush=True)
    if not args.no_browser and frontend_running():
        threading.Timer(1.0, webbrowser.open, [settings.FRONTEND_URL]).start()
    try:
        laptop.run()
    except KeyboardInterrupt:
        pass
    finally:
        phone.should_exit = True
        phone_thread.join(timeout=5)


if __name__ == "__main__":
    main()
