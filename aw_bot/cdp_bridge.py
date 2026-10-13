import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import websockets

from .logs import LOG

_CDP_TIMEOUT = 30.0


class _Upstream:
    def __init__(self, ws_url: str, loop: asyncio.AbstractEventLoop) -> None:
        self.ws_url = ws_url
        self.loop = loop
        self.ws = None

        self.closed_reason: str | None = None
        self.opened_at: float = 0.0
        self.closed_at: float = 0.0

        self._next_id = 1
        self._pending: dict[int, tuple] = {}

        self._session_owner: dict[str, object] = {}
        self._browser_clients: set = set()

    async def connect(self) -> None:
        self.ws = await websockets.connect(
            self.ws_url, max_size=None, open_timeout=60, ping_interval=None
        )
        self.opened_at = time.time()
        asyncio.ensure_future(self._pump())

    async def close(self) -> None:
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:
                pass

    def _take_id(self) -> int:
        self._next_id += 1
        return self._next_id

    async def call(self, method: str, params: dict | None = None, session_id: str | None = None):
        uid = self._take_id()
        future = self.loop.create_future()
        self._pending[uid] = ("self", future)
        msg = {"id": uid, "method": method, "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id
        await self.ws.send(json.dumps(msg))
        return await asyncio.wait_for(future, _CDP_TIMEOUT)

    async def forward(self, raw: str, client, session_id: str | None) -> None:
        try:
            msg = json.loads(raw)
        except ValueError:
            return

        client_id = msg.get("id")
        uid = self._take_id()
        msg["id"] = uid

        strip_session = False
        if session_id and "sessionId" not in msg:
            msg["sessionId"] = session_id
            strip_session = True

        self._pending[uid] = ("client", client, client_id, strip_session)
        await self.ws.send(json.dumps(msg))

    async def _pump(self) -> None:
        try:
            async for raw in self.ws:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue

                uid = msg.get("id")
                if uid is not None and uid in self._pending:
                    entry = self._pending.pop(uid)
                    if entry[0] == "self":
                        future = entry[1]
                        if not future.done():
                            if "error" in msg:
                                future.set_exception(
                                    RuntimeError(f"CDP error: {msg['error']}")
                                )
                            else:
                                future.set_result(msg.get("result", {}))
                        continue

                    _, client, client_id, strip_session = entry
                    msg["id"] = client_id
                    if strip_session:
                        msg.pop("sessionId", None)
                    await self._send(client, msg)
                    continue

                sid = msg.get("sessionId")
                if sid and sid in self._session_owner:
                    owner = self._session_owner[sid]
                    if getattr(owner, "bridge_session_id", None) == sid:
                        msg.pop("sessionId", None)
                    await self._send(owner, msg)
                    continue

                for client in list(self._browser_clients):
                    await self._send(client, msg)
        except Exception as exc:
            LOG.debug("CDP upstream closed: %s", exc)
            self.closed_reason = f"{type(exc).__name__}: {exc}"
        finally:
            if self.closed_at == 0.0:
                self.closed_at = time.time()
            if self.closed_reason is None:
                self.closed_reason = "the remote closed the connection"

            for client in list(self._browser_clients) + list(self._session_owner.values()):
                try:
                    await client.close()
                except Exception:
                    pass

    @staticmethod
    async def _send(client, msg: dict) -> None:
        try:
            await client.send(json.dumps(msg))
        except Exception:
            pass


class CdpBridge:
    def __init__(self, ws_url: str) -> None:
        self.ws_url = ws_url
        self.loop = asyncio.new_event_loop()
        self.upstream = _Upstream(ws_url, self.loop)
        self.ws_port = 0
        self.http_port = 0

        self.session_timeout_ms = 0
        self._thread: threading.Thread | None = None
        self._http: ThreadingHTTPServer | None = None
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._ws_server = None

    def start(self) -> str:
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        if not self._ready.wait(90):
            raise RuntimeError("CDP bridge did not start within 90s")
        if self._error is not None:
            raise self._error

        self._http = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self.http_port = self._http.server_port
        threading.Thread(target=self._http.serve_forever, daemon=True).start()

        LOG.debug(
            "CDP bridge: http 127.0.0.1:%d, ws 127.0.0.1:%d",
            self.http_port, self.ws_port,
        )
        return f"127.0.0.1:{self.http_port}"

    @property
    def browser_version(self) -> str:
        product = self._call("Browser.getVersion").get("product", "")
        return product.split("/", 1)[1].strip() if "/" in product else ""

    def call(self, method: str, params: dict | None = None,
             session_id: str | None = None) -> dict:
        return self._call(method, params, session_id)

    @property
    def upstream_closed(self) -> bool:
        return self.upstream.closed_reason is not None

    @property
    def session_seconds(self) -> float:
        if not self.upstream.opened_at:
            return 0.0
        end = self.upstream.closed_at or time.time()
        return end - self.upstream.opened_at

    def stop(self) -> None:
        if self._http is not None:
            try:
                self._http.shutdown()
            except Exception:
                pass
        if self.loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self._shutdown(), self.loop).result(10)
            except Exception:
                pass
            self.loop.call_soon_threadsafe(self.loop.stop)

    async def _shutdown(self) -> None:
        if self._ws_server is not None:
            self._ws_server.close()
            try:
                await self._ws_server.wait_closed()
            except Exception:
                pass
        await self.upstream.close()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._serve())
        except BaseException as exc:
            self._error = exc
            self._ready.set()
            return
        self.loop.run_forever()

    async def _serve(self) -> None:
        await self.upstream.connect()
        self._ws_server = await websockets.serve(
            self._client, "127.0.0.1", 0, max_size=None, ping_interval=None
        )
        self.ws_port = next(iter(self._ws_server.sockets)).getsockname()[1]
        self._ready.set()

    async def _client(self, client) -> None:
        path = getattr(client, "path", "") or getattr(
            getattr(client, "request", None), "path", ""
        )
        session_id = None

        if "/devtools/page/" in path:
            target_id = path.rsplit("/", 1)[-1]
            try:
                result = await self.upstream.call(
                    "Target.attachToTarget", {"targetId": target_id, "flatten": True}
                )
            except Exception as exc:
                LOG.debug("CDP bridge could not attach to %s: %s", target_id, exc)
                return
            session_id = result.get("sessionId")
            client.bridge_session_id = session_id
            self.upstream._session_owner[session_id] = client
        else:
            self.upstream._browser_clients.add(client)

        try:
            async for raw in client:
                await self.upstream.forward(raw, client, session_id)
        except Exception as exc:
            LOG.debug("CDP bridge client ended: %s", exc)
        finally:
            self.upstream._browser_clients.discard(client)
            if session_id:
                self.upstream._session_owner.pop(session_id, None)

    def _call(self, method: str, params: dict | None = None,
              session_id: str | None = None):
        return asyncio.run_coroutine_threadsafe(
            self.upstream.call(method, params, session_id), self.loop
        ).result(_CDP_TIMEOUT + 5)

    def _version(self) -> dict:
        info = self._call("Browser.getVersion")

        revision = info.get("revision", "")
        webkit = "537.36"
        agent = info.get("userAgent", "")
        if "AppleWebKit/" in agent:
            webkit = agent.split("AppleWebKit/", 1)[1].split(" ", 1)[0]
        if revision and not revision.startswith("@"):
            revision = "@" + revision

        return {
            "Browser": info.get("product", ""),
            "Protocol-Version": info.get("protocolVersion", "1.3"),
            "User-Agent": agent,
            "V8-Version": info.get("jsVersion", ""),
            "WebKit-Version": f"{webkit} ({revision})" if revision else webkit,
            "webSocketDebuggerUrl": f"ws://127.0.0.1:{self.ws_port}/devtools/browser/bridge",
        }

    def _list(self) -> list:
        targets = self._call("Target.getTargets").get("targetInfos", [])
        pages = []
        for t in targets:
            if t.get("type") != "page":
                continue
            tid = t.get("targetId")
            pages.append({
                "description": "",
                "devtoolsFrontendUrl": "",
                "id": tid,
                "title": t.get("title", ""),
                "type": "page",
                "url": t.get("url", ""),
                "webSocketDebuggerUrl": f"ws://127.0.0.1:{self.ws_port}/devtools/page/{tid}",
            })
        return pages

    def _handler_class(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args) -> None:
                pass

            def _json(self, payload, status: int = 200) -> None:
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=UTF-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                path = urlparse(self.path).path.rstrip("/")
                try:
                    if path in ("/json/version",):
                        self._json(bridge._version())
                    elif path in ("/json", "/json/list"):
                        self._json(bridge._list())
                    elif path.startswith("/json/new"):
                        url = urlparse(self.path).query or "about:blank"
                        tid = bridge._call("Target.createTarget", {"url": url}).get("targetId")
                        self._json({
                            "id": tid, "type": "page", "url": url, "title": "",
                            "webSocketDebuggerUrl":
                                f"ws://127.0.0.1:{bridge.ws_port}/devtools/page/{tid}",
                        })
                    elif path.startswith("/json/close/"):
                        bridge._call("Target.closeTarget", {"targetId": path.rsplit("/", 1)[-1]})
                        self._json("Target is closing")
                    elif path.startswith("/json/activate/"):
                        bridge._call("Target.activateTarget", {"targetId": path.rsplit("/", 1)[-1]})
                        self._json("Target activated")
                    else:
                        self._json({"error": "not found"}, status=404)
                except Exception as exc:
                    LOG.debug("CDP bridge HTTP %s failed: %s", path, exc)
                    self._json({"error": str(exc)}, status=500)

            def do_PUT(self) -> None:
                self.do_GET()

        return Handler
