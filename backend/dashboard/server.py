"""The two web apps: the laptop API (this laptop only, http) and the phone pages (the Wi-Fi, https).

The laptop API serves the Next.js app in frontend/ (accounts, voice checks, Track your voice, phone linking).
They share the database, but each only has its own routes: a phone can pair, record and send, never reach
the accounts or the laptop API.
"""
import functools
import logging
from pathlib import Path

import segno
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from backend import settings
from backend.dashboard import auth, checks, db, notify, tracking
from voice_checker.audio.quality import QualityError
from voice_checker.texts import TEXTS

log = logging.getLogger("dashboard")
STATIC = Path(__file__).parent / "static"
COOKIES = {"laptop": ("vd_session", settings.LAPTOP_SESSION_DAYS), "phone": ("vd_phone", settings.PHONE_SESSION_DAYS)}
SIGNED_OUT = {"laptop": "Please sign in again.",
              "phone": "This phone isn't linked any more. Scan the QR code on your laptop's dashboard."}


# --- Helpers ----------------------------------------------------------------
class Guard:
    """Refuse state-changing requests sent from other websites (CSRF), and add basic security headers."""
    HEADERS = [(b"x-frame-options", b"DENY"), (b"referrer-policy", b"no-referrer"),
               (b"x-content-type-options", b"nosniff")]

    def __init__(self, app, trusted=()):
        self.app = app
        self.trusted = set(trusted)  # other origins allowed to send requests: the Next.js app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope)
        origin = request.headers.get("origin")
        own = f"{request.url.scheme}://{request.url.netloc}"
        if scope["method"] not in ("GET", "HEAD") and origin and origin != own and origin not in self.trusted:
            return await JSONResponse({"error": "Refused a request from another website."}, 403)(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), *self.HEADERS]
            await send(message)

        await self.app(scope, receive, send_with_headers)


def page(name):
    return FileResponse(STATIC / name, headers={"Cache-Control": "no-store"})


def error(message, status=400):
    return JSONResponse({"error": message}, status_code=status)


async def json_body(request):
    try:
        data = await request.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def signed_in(request, kind):
    """The session's user row (id, name, email, session_id, device), or None."""
    token = request.cookies.get(COOKIES[kind][0])
    return db.session_user(auth.token_hash(token), kind) if token else None


def needs(kind):
    """Endpoint decorator: 401 unless signed in (laptop) or linked (phone); the user is in request.state.user."""
    def wrap(endpoint):
        @functools.wraps(endpoint)
        async def inner(request):
            request.state.user = signed_in(request, kind)
            if request.state.user is None:
                return error(SIGNED_OUT[kind], 401)
            return await endpoint(request)
        return inner
    return wrap


def start_session(response, user_id, kind, device=None):
    """Create a session and put its token in the response's cookie."""
    token, digest = auth.new_token()
    name, days = COOKIES[kind]
    db.create_session(user_id, kind, digest, days, device)
    response.set_cookie(name, token, max_age=days * 86400, httponly=True, samesite="lax", secure=kind == "phone")
    return response


def end_session(request, response, kind):
    name = COOKIES[kind][0]
    if token := request.cookies.get(name):
        db.delete_session(auth.token_hash(token))
    response.delete_cookie(name)
    return response


def device_name(user_agent):
    """'iPhone · Safari', 'Android phone · Chrome', ... from a User-Agent header."""
    systems = [("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android phone"), ("Windows", "Windows PC"),
               ("Macintosh", "Mac"), ("Linux", "Linux")]
    browsers = [("SamsungBrowser", "Samsung Internet"), ("EdgA", "Edge"), ("Edg/", "Edge"), ("FxiOS", "Firefox"),
                ("Firefox", "Firefox"), ("CriOS", "Chrome"), ("Chrome", "Chrome"), ("Safari", "Safari")]
    system = next((name for key, name in systems if key in user_agent), "Phone")
    browser = next((name for key, name in browsers if key in user_agent), None)
    return f"{system} · {browser}" if browser else system


async def receive_check(request, user, device):
    """Read a recording from the request body (the raw audio) and queue its check; the JSON response."""
    mode, text_id = request.query_params.get("mode"), request.query_params.get("text")
    if mode not in ("reading", "vowel") or (mode == "reading" and text_id not in TEXTS):
        return error("Unknown recording type. Reload the page and try again.")
    if checks.tasks()[mode] is None:
        return error("This check isn't available on the laptop yet: its model isn't trained.", 409)
    audio = await read_audio(request)
    if isinstance(audio, JSONResponse):
        return audio
    user = {**dict(user), "device": device}
    check_id = db.add_check(user, mode, text_id if mode == "reading" else None)
    checks.submit(check_id, user, mode, audio)
    log.info("Check %s received from %s (%s, %.0f kB)", check_id, device, mode, len(audio) / 1024)
    return JSONResponse({"id": check_id}, status_code=202)


async def read_audio(request):
    """The request body as bytes, or an error response (wrong type, empty, too large)."""
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith(("audio/", "application/octet-stream")):
        return error("Please send an audio recording.", 415)
    limit, audio = settings.MAX_UPLOAD_MB * 2**20, bytearray()
    async for chunk in request.stream():
        audio += chunk
        if len(audio) > limit:
            return error(f"The recording is larger than {settings.MAX_UPLOAD_MB} MB. Please send a shorter one.", 413)
    if not audio:
        return error("The recording is empty. Please record again.")
    return bytes(audio)


def text_title(text_id):
    return TEXTS.get(text_id or "", {}).get("title")


def shown_path(path):
    """A path relative to the project when it is inside it (data\\outbox), else in full."""
    return str(path.relative_to(settings.ROOT)) if path.is_relative_to(settings.ROOT) else str(path)


# --- Dashboard (laptop) -----------------------------------------------------
def laptop_app(addresses):
    """The API behind the Next.js app. `addresses`: this laptop's Wi-Fi addresses for the QR code, the default first."""

    async def to_frontend(request):
        """The pages are in the Next.js app; old bookmarks of this server land there."""
        path = {"/login": "/login", "/signup": "/signup"}.get(request.url.path, "/")
        return RedirectResponse(settings.FRONTEND_URL + path, 303)

    async def me(request):
        user = signed_in(request, "laptop")
        if user is None:
            return error(SIGNED_OUT["laptop"], 401)
        return JSONResponse({"name": user["name"], "email": user["email"]})

    async def signup(request):
        form = await json_body(request)
        name, email = str(form.get("name", "")).strip(), str(form.get("email", "")).strip().lower()
        password = str(form.get("password", ""))
        if problem := auth.account_problem(name, email, password):
            return error(problem)
        user_id = db.create_user(name, email, await run_in_threadpool(auth.hash_password, password))
        if user_id is None:
            return error("There is already an account with this email. Sign in instead.", 409)
        log.info("New account: %s", email)
        return start_session(JSONResponse({"ok": True}), user_id, "laptop")

    async def login(request):
        form = await json_body(request)
        user = db.user_by_email(str(form.get("email", "")).strip().lower())
        password = str(form.get("password", ""))
        if user is None or not await run_in_threadpool(auth.check_password, password, user["password"]):
            return error("Wrong email or password.", 401)
        return start_session(JSONResponse({"ok": True}), user["id"], "laptop")

    async def logout(request):
        return end_session(request, JSONResponse({"ok": True}), "laptop")

    @needs("laptop")
    async def overview(request):
        """Everything the dashboard shows; it polls this every few seconds."""
        user = request.state.user
        smtp = notify.smtp_settings()
        return JSONResponse({
            "user": {"name": user["name"], "email": user["email"]},
            "phones": [dict(p) for p in db.phones(user["id"])],
            "checks": [{**c, "text_title": text_title(c["text_id"])} for c in db.checks(user["id"])],
            "engine": checks.state["engine"],
            "modes": {mode: task is not None for mode, task in checks.tasks().items()},
            "email": {"configured": smtp is not None, "server": smtp["host"] if smtp else None,
                      "outbox": shown_path(settings.OUTBOX_DIR)},
            "addresses": addresses,
        })

    @needs("laptop")
    async def new_pairing(request):
        """A fresh one-time QR code; the user's previous code stops working."""
        form = await json_body(request)
        address = form.get("address") if form.get("address") in addresses else addresses[0]
        token, digest = auth.new_token()
        db.create_pairing(request.state.user["id"], digest, settings.PAIRING_TTL_S)
        url = f"https://{address}:{settings.PHONE_PORT}/pair/{token}"
        svg = segno.make(url, error="m", micro=False).svg_inline(dark="#1e1a16", light=None, border=0, omitsize=True)
        return JSONResponse({"url": url, "svg": svg, "address": address, "phone_url": f"https://{address}:{settings.PHONE_PORT}",
                             "expires_in": settings.PAIRING_TTL_S})

    @needs("laptop")
    async def unlink_phone(request):
        if not db.unlink_phone(request.state.user["id"], request.path_params["id"]):
            return error("That phone isn't linked.", 404)
        return JSONResponse({"ok": True})

    async def texts(request):
        return JSONResponse([{"id": k, "title": t["title"], "text": t["text"]} for k, t in TEXTS.items()])

    @needs("laptop")
    async def new_check(request):
        """A voice check recorded or uploaded in the browser on this laptop."""
        return await receive_check(request, request.state.user, notify.LAPTOP_DEVICE)

    @needs("laptop")
    async def get_check(request):
        check = db.check(request.path_params["id"], request.state.user["id"])
        if check is None:
            return error("Check not found.", 404)
        return JSONResponse({**check, "text_title": text_title(check["text_id"])})

    @needs("laptop")
    async def tracking_texts(request):
        return JSONResponse(tracking.texts(request.state.user["id"]))

    def known_text(request):
        text_id = request.path_params["text"]
        return text_id if text_id in TEXTS else None

    @needs("laptop")
    async def tracking_state(request):
        if not (text_id := known_text(request)):
            return error("Unknown text.", 404)
        return JSONResponse(await run_in_threadpool(tracking.state, request.state.user["id"], text_id))

    @needs("laptop")
    async def tracking_add(request):
        """Analyze and store a reading (takes a few seconds: transcript, pitch, pauses, voice signature)."""
        if not (text_id := known_text(request)):
            return error("Unknown text.", 404)
        audio = await read_audio(request)
        if isinstance(audio, JSONResponse):
            return audio
        try:
            return JSONResponse(await run_in_threadpool(tracking.add_reading, request.state.user["id"], text_id, audio))
        except QualityError as e:
            return error(str(e), 422)

    @needs("laptop")
    async def tracking_clear(request):
        if not (text_id := known_text(request)):
            return error("Unknown text.", 404)
        db.delete_readings(request.state.user["id"], text_id)
        return JSONResponse(await run_in_threadpool(tracking.state, request.state.user["id"], text_id))

    @needs("laptop")
    async def tracking_demo(request):
        return JSONResponse(await run_in_threadpool(tracking.load_demo, request.state.user["id"]))

    @needs("laptop")
    async def email_test(request):
        user = request.state.user
        subject, body = notify.test_email(user["name"])
        try:
            outcome = await run_in_threadpool(notify.send, user["email"], subject, body)
        except Exception as e:
            return error(f"The email couldn't be sent: {e}", 502)
        return JSONResponse({"outcome": outcome, "to": user["email"]})

    routes = [
        Route("/", to_frontend),
        Route("/login", to_frontend),
        Route("/signup", to_frontend),
        Route("/dashboard", to_frontend),
        Route("/api/me", me),
        Route("/api/signup", signup, methods=["POST"]),
        Route("/api/login", login, methods=["POST"]),
        Route("/api/logout", logout, methods=["POST"]),
        Route("/api/dashboard", overview),
        Route("/api/pairing", new_pairing, methods=["POST"]),
        Route("/api/phones/{id:int}", unlink_phone, methods=["DELETE"]),
        Route("/api/email-test", email_test, methods=["POST"]),
        Route("/api/texts", texts),
        Route("/api/checks", new_check, methods=["POST"]),
        Route("/api/checks/{id:int}", get_check),
        Route("/api/tracking", tracking_texts),
        Route("/api/tracking/demo", tracking_demo, methods=["POST"]),
        Route("/api/tracking/{text}", tracking_state),
        Route("/api/tracking/{text}", tracking_add, methods=["POST"]),
        Route("/api/tracking/{text}", tracking_clear, methods=["DELETE"]),
    ]
    return Starlette(routes=routes, middleware=[
        Middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"]),
        Middleware(Guard, trusted=[settings.FRONTEND_URL])])


# --- Phone pages (Wi-Fi) ----------------------------------------------------
def phone_app(addresses):
    """Pairing, recording and sending. Reached over HTTPS on this laptop's Wi-Fi `addresses`."""

    async def home(request):
        return RedirectResponse("/phone", 303)

    async def phone_page(request):
        return page("phone.html")

    async def pairing_info(request):
        name = db.pairing_owner(auth.token_hash(request.path_params["token"]))
        if name is None:
            return error("This QR code has expired or was already used. Show a new one on your laptop's dashboard.", 410)
        return JSONResponse({"name": name})

    async def pair(request):
        """Use a QR code's one-time token: this phone gets its own session for the dashboard's user."""
        user_id = db.use_pairing(auth.token_hash(request.path_params["token"]))
        if user_id is None:
            return error("This QR code has expired or was already used. Show a new one on your laptop's dashboard.", 410)
        device = device_name(request.headers.get("user-agent", ""))
        response = end_session(request, JSONResponse({"ok": True}), "phone")  # replaces an older link of this phone
        log.info("Phone linked: %s", device)
        return start_session(response, user_id, "phone", device)

    @needs("phone")
    async def info(request):
        user = request.state.user
        return JSONResponse({
            "name": user["name"], "device": user["device"],
            "texts": [{"id": k, "title": t["title"], "text": t["text"]} for k, t in TEXTS.items()],
            "modes": {mode: task is not None for mode, task in checks.tasks().items()},
            "max_mb": settings.MAX_UPLOAD_MB,
        })

    @needs("phone")
    async def send(request):
        """Receive a recording (the raw audio is the request body) and queue its check."""
        return await receive_check(request, request.state.user, request.state.user["device"])

    @needs("phone")
    async def check_status(request):
        check = db.check(request.path_params["id"], request.state.user["id"])
        return JSONResponse(check) if check else error("Check not found.", 404)

    async def unlink(request):
        return end_session(request, JSONResponse({"ok": True}), "phone")

    routes = [
        Route("/", home),
        Route("/phone", phone_page),
        Route("/pair/{token}", phone_page),
        Route("/api/pair/{token}", pairing_info),
        Route("/api/pair/{token}", pair, methods=["POST"]),
        Route("/api/phone", info),
        Route("/api/phone/checks", send, methods=["POST"]),
        Route("/api/phone/checks/{id:int}", check_status),
        Route("/api/phone/unlink", unlink, methods=["POST"]),
        Mount("/static", StaticFiles(directory=STATIC)),
    ]
    return Starlette(routes=routes, middleware=[
        Middleware(TrustedHostMiddleware, allowed_hosts=[*addresses, "localhost", "127.0.0.1"]), Middleware(Guard)])
