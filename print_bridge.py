"""Quick Print oficial: um código temporário, sem chaves ou SDK no navegador."""
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class PrintBridgeError(Exception):
    pass


def send_to_android(code, text):
    # O host é fixo; somente os 12 dígitos validados entram no caminho.
    if not isinstance(code, str) or len(code) != 12 or not code.isascii() or not code.isdigit():
        raise PrintBridgeError("Digite o código de 12 dígitos mostrado no Android.")
    base = f"https://bluetoothprinterplus.firebaseio.com/printFromAnywhere/{code}"

    def exchange(url, payload=None, headers=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(url, data=data, method="GET" if data is None else "PUT",
                          headers={"Content-Type": "application/json", **(headers or {})})
        with urlopen(request, timeout=8) as response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise PrintBridgeError("Resposta inválida do serviço de impressão.")
            return json.loads(raw), response.headers.get("ETag")

    try:
        receiving, _ = exchange(base + ".json")
        if not isinstance(receiving, dict):
            raise PrintBridgeError("Código expirado. Mantenha Print From Anywhere aberto no Android e confira o código.")
        devices = receiving.get("availableDevices") or {}
        if not isinstance(devices, dict) or not devices:
            raise PrintBridgeError("Conecte a impressora no aplicativo Android antes de imprimir.")
        target = receiving.get("connectedDeviceAddress")
        if not isinstance(target, str) or target not in devices:
            target = receiving.get("defaultDevice")
        if not isinstance(target, str) or target not in devices:
            target = next(iter(devices)) if len(devices) == 1 else None
        if not target:
            raise PrintBridgeError("Escolha a impressora conectada no aplicativo Android antes de imprimir.")
        previous, etag = exchange(base + "/job.json", headers={"X-Firebase-ETag": "true"})
        if previous is not None and (not isinstance(previous, dict) or previous.get("status") not in {"printed", "error"}):
            raise PrintBridgeError("O Android ainda tem uma impressão pendente. Confira o aparelho antes de reenviar.")
        if not etag:
            raise PrintBridgeError("O serviço não confirmou disponibilidade. Nenhum novo envio foi feito.")
        job = {"status": "pending", "createdAt": int(time.time() * 1000), "text": text}
        if target:
            job["targetDevice"] = target
        # If-Match evita sobrescrever um trabalho recebido depois da consulta.
        exchange(base + "/job.json", job, {"If-Match": etag})
    except HTTPError as error:
        if error.code == 412:
            raise PrintBridgeError("Outra impressão começou no Android. Aguarde antes de reenviar.") from None
        raise PrintBridgeError("O serviço recusou o envio. Confira o código e o aplicativo Android.") from None
    except (URLError, TimeoutError, OSError, ValueError, TypeError):
        # shortcut: sem confirmação de entrega, conferir o papel antes de repetir; nunca reenviar sozinho.
        raise PrintBridgeError("Resposta incerta do serviço. Confira a impressora antes de tentar novamente.") from None
