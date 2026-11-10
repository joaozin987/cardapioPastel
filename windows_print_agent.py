from __future__ import annotations

import asyncio
import secrets
import threading
from typing import Any

from flask import Flask, abort, redirect, render_template_string, request, session, url_for
from serial import Serial
from serial.tools import list_ports

try:
    from bleak import BleakClient, BleakScanner
except ImportError:
    BleakClient = None
    BleakScanner = None

HOST = "127.0.0.1"
PORT = 8765
BAUDRATE = 9600

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict")

connection: dict[str, Any] = {"kind": None, "handle": None, "label": None}
ble_devices: dict[str, dict[str, str]] = {}
ble_controller = None


class BleController:
    """Mantém um event loop para preservar a conexão BLE entre requisições."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.ready.wait(timeout=5)

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.ready.set()
        self.loop.run_forever()

    def submit(self, coroutine, timeout=20):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout=timeout)

    async def scan(self):
        if BleakScanner is None:
            raise RuntimeError("BLE indisponível. Instale as dependências do agente.")
        devices = await BleakScanner.discover(timeout=6)
        return [{"name": d.name or "Dispositivo sem nome", "address": d.address} for d in devices]

    async def connect(self, address):
        if BleakClient is None:
            raise RuntimeError("BLE indisponível. Instale as dependências do agente.")
        await self.disconnect()
        client = BleakClient(address, timeout=15)
        await client.connect()
        if not client.is_connected:
            raise RuntimeError("O dispositivo não confirmou a conexão.")
        return client

    async def disconnect(self):
        handle = connection.get("handle")
        if connection.get("kind") == "ble" and handle is not None and handle.is_connected:
            await handle.disconnect()


def get_ble_controller():
    global ble_controller
    if ble_controller is None:
        ble_controller = BleController()
    return ble_controller


def close_connection():
    kind, handle = connection.get("kind"), connection.get("handle")
    if kind == "serial" and handle is not None:
        try:
            if handle.is_open:
                handle.close()
        except Exception:
            pass
    elif kind == "ble" and handle is not None and ble_controller is not None:
        try:
            ble_controller.submit(ble_controller.disconnect(), timeout=10)
        except Exception:
            pass
    connection.update(kind=None, handle=None, label=None)


def status():
    kind, handle = connection.get("kind"), connection.get("handle")
    if kind == "serial" and handle is not None and handle.is_open:
        return "Conectada pela porta serial " + str(connection["label"])
    if kind == "ble" and handle is not None and handle.is_connected:
        return "Conectada por Bluetooth BLE: " + str(connection["label"])
    if kind:
        close_connection()
    return "Nenhuma impressora conectada"


def ports():
    return [{"device": p.device, "description": p.description or "Porta serial"}
            for p in list_ports.comports()]


def token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def verify_token():
    if not secrets.compare_digest(session.get("csrf_token", ""), request.form.get("csrf_token", "")):
        abort(400, description="Sessão local inválida. Atualize a página.")


PAGE = """
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>D&A Lanche's — Conectar impressora</title>
<style>
body{font-family:Arial,sans-serif;background:#f3f4f6;color:#172033;margin:0;padding:24px 14px}
main{max-width:720px;margin:auto}header,section{background:white;border:1px solid #ddd;border-radius:12px;padding:18px;margin-bottom:14px}
h1{margin:0 0 6px}h2{font-size:19px}.status{background:#ecfdf5;padding:12px;border-radius:8px;font-weight:bold}
.item{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid #eee}
small{display:block;color:#596579;overflow-wrap:anywhere}button{border:0;border-radius:8px;padding:10px 14px;background:#172033;color:white;font-weight:bold}
.secondary{background:#e5e7eb;color:#172033}.danger{background:#b42318}.message{padding:12px;background:#eff6ff;border-radius:8px}
.warning{background:#fff7ed;color:#9a3412;padding:12px;border-radius:8px}
@media(max-width:520px){.item{align-items:flex-start;flex-direction:column}}
</style></head><body><main>
<header><h1>D&A Lanche's</h1><p>Assistente local de conexão</p><div class="status">{{ status }}</div>
{% if connected %}<form method="post" action="/disconnect"><input type="hidden" name="csrf_token" value="{{ token }}"><button class="danger">Desconectar</button></form>{% endif %}</header>
{% if message %}<p class="message">{{ message }}</p>{% endif %}
<section><h2>Bluetooth clássico — portas COM</h2>
<p>Impressoras pareadas no Windows por Bluetooth SPP normalmente aparecem como portas COM.</p>
{% for p in ports %}<div class="item"><div><b>{{ p.device }}</b><small>{{ p.description }}</small></div>
<form method="post" action="/connect-serial"><input type="hidden" name="csrf_token" value="{{ token }}"><input type="hidden" name="port" value="{{ p.device }}"><button>Conectar</button></form></div>{% else %}
<p>Nenhuma porta serial encontrada.</p>{% endfor %}</section>
<section><h2>Bluetooth BLE</h2><p>Procura dispositivos Bluetooth Low Energy. A descoberta não identifica o protocolo de impressão.</p>
<form method="post" action="/scan-ble"><input type="hidden" name="csrf_token" value="{{ token }}"><button class="secondary">Procurar dispositivos BLE</button></form>
{% for d in devices %}<div class="item"><div><b>{{ d.name }}</b><small>{{ d.address }}</small></div>
<form method="post" action="/connect-ble"><input type="hidden" name="csrf_token" value="{{ token }}"><input type="hidden" name="address" value="{{ d.address }}"><button>Conectar</button></form></div>{% else %}
{% if scanned %}<p>Nenhum dispositivo BLE encontrado nesta busca.</p>{% endif %}{% endfor %}</section>
<section class="warning"><b>Importante:</b> esta versão testa descoberta e conexão. Não envia pedidos nem dados de impressão. Conectar não confirma compatibilidade com ESC/POS ou outro protocolo.</section>
<small>Serviço local em 127.0.0.1:8765. Não exponha este serviço à rede ou à internet.</small>
</main></body></html>
"""


def page(message="", scanned=False):
    return render_template_string(PAGE, status=status(), connected=connection["kind"] is not None,
                                  ports=ports(), devices=list(ble_devices.values()),
                                  scanned=scanned, message=message, token=token())


@app.get("/")
def index():
    return page(request.args.get("message", ""))


@app.post("/scan-ble")
def scan_ble():
    verify_token()
    try:
        found = get_ble_controller().submit(get_ble_controller().scan(), timeout=15)
        ble_devices.clear()
        ble_devices.update({d["address"]: d for d in found})
        return page(f"Busca concluída: {len(found)} dispositivo(s) BLE encontrado(s).", scanned=True)
    except Exception as exc:
        return page(f"Falha na busca BLE: {exc}", scanned=True)


@app.post("/connect-serial")
def connect_serial():
    verify_token()
    port = request.form.get("port", "")
    if port not in {p["device"] for p in ports()}:
        return page("A porta selecionada não está mais disponível. Atualize a página.")
    try:
        close_connection()
        handle = Serial(port=port, baudrate=BAUDRATE, timeout=1, write_timeout=1)
        connection.update(kind="serial", handle=handle, label=port)
        return page(f"Porta {port} aberta. Nenhum dado foi enviado.")
    except Exception as exc:
        close_connection()
        return page(f"Não foi possível abrir {port}: {exc}")


@app.post("/connect-ble")
def connect_ble():
    verify_token()
    address = request.form.get("address", "")
    if address not in ble_devices:
        return page("Dispositivo não reconhecido. Faça uma nova busca BLE.")
    try:
        close_connection()
        handle = get_ble_controller().submit(get_ble_controller().connect(address), timeout=25)
        label = ble_devices[address]["name"]
        connection.update(kind="ble", handle=handle, label=label)
        return page(f"Conexão BLE estabelecida com {label}. Nenhum dado foi enviado.", scanned=True)
    except Exception as exc:
        close_connection()
        return page(f"Não foi possível conectar ao dispositivo BLE: {exc}", scanned=True)


@app.post("/disconnect")
def disconnect():
    verify_token()
    close_connection()
    return redirect(url_for("index", message="Dispositivo desconectado."))


if __name__ == "__main__":
    print("Agente local em http://127.0.0.1:8765 — mantenha esta janela aberta.")
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
