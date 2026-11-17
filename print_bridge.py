"""Quick Print oficial: um código temporário, sem chaves ou SDK no navegador."""
import json
import unicodedata
import re
import time
import textwrap
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class PrintBridgeError(Exception):
    pass


def _large_receipt_lines(text):
    """Converte a nota de 32 colunas em linhas grandes para a térmica de 58 mm."""
    segments = []
    section = 0
    small_item = False
    item_count = 0
    for line in text.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        if line.strip() == "-" * 32:
            segments.append({"divider": True})
            section += 1
            continue

        is_item = section == 1
        indent = len(line) - len(line.lstrip())
        content = unicodedata.normalize("NFKD", line.strip()).encode("ascii", "ignore").decode("ascii")
        # Versões abertas antes da atualização ainda podem enviar a data e hora.
        if section == 0 and re.fullmatch(r"(?:\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2})?|\d{1,2}:\d{2})", content):
            continue
        if is_item:
            content = re.sub(r"^(\d+x)\s+pastel\s+(?:de\s+)?mist(?:ão|ao)$", r"\1 Mistao", content, flags=re.IGNORECASE)
            content = re.sub(r"^(\d+x)\s+pastel\s+(?:de\s+)?mist[ou]$", r"\1 Misto", content, flags=re.IGNORECASE)
        quantity, separator, _ = content.partition(" ")
        if is_item and separator and quantity.endswith("x") and quantity[:-1].isdigit():
            name = content.split(" ", 1)[1].casefold()
            small_item = name.startswith("pastel ") or name in {"misto", "mistão", "mistao", "queijo", "frango com queijo", "frango com catupiry"}
            if item_count:
                segments.append({"text": "", "align": "left", "doubleSize": False})
            item_count += 1
            indent = len(quantity) + 1
            initial_indent = ""
        else:
            initial_indent = " " * min(indent, 5) if is_item else ""

        for part in textwrap.wrap(
            content,
            width=(28 if small_item else 14) if is_item else 32,
            initial_indent=initial_indent,
            subsequent_indent=" " * min(indent, 5) if is_item else "",
        ):
            segments.append({
                "text": part,
                "align": "left" if is_item else "center",
                "bold": is_item or content.startswith("PEDIDO #"),
                "underline": False,
                "doubleSize": is_item and not small_item,
            })
    return segments


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
        job = {
            "status": "pending",
            "createdAt": int(time.time() * 1000),
            "richText": _large_receipt_lines(text),
            "strictMode": False,
        }
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
