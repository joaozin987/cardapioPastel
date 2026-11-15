"""Quick Print oficial: um código temporário, sem chaves ou SDK no navegador."""
from io import BytesIO
import json
import time
import textwrap
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont


class PrintBridgeError(Exception):
    pass


def _large_receipt_lines(text):
    """Converte a nota de 32 colunas em linhas grandes para a térmica de 58 mm."""
    segments = []
    section = 0
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
        content = line.strip()
        quantity, separator, _ = content.partition(" ")
        if is_item and separator and quantity.endswith("x") and quantity[:-1].isdigit():
            indent = len(quantity) + 1
            initial_indent = ""
        else:
            initial_indent = " " * min(indent, 5) if is_item else ""

        for part in textwrap.wrap(
            content,
            width=16,
            initial_indent=initial_indent,
            subsequent_indent=" " * min(indent, 5) if is_item else "",
        ):
            segments.append({
                "text": part,
                "align": "left" if is_item else "center",
                "bold": is_item or content.startswith("PEDIDO #"),
                "underline": False,
                "doubleSize": True,
            })
    return segments


def _receipt_png(text):
    # Uma térmica de 203 dpi usa aproximadamente 8 pixels por milímetro.
    width, margin = 384, 10
    body_font = ImageFont.load_default(size=round(27 * 203 / 72))
    meta_font = ImageFont.load_default(size=round(16 * 203 / 72))
    section = 0
    blocks = []
    for line in text.splitlines():
        content = line.strip()
        if not content:
            continue
        if content == "-" * 32:
            blocks.append((None, False, None))
            section += 1
        elif section == 1 and line[0].isspace() and blocks and blocks[-1][0] is not None:
            old, _, _ = blocks[-1]
            blocks[-1] = (old + " " + content, False, body_font)
        else:
            font = body_font if section == 1 or content.startswith("PEDIDO #") else meta_font
            blocks.append((content, section != 1, font))

    rows = []
    height = margin
    for content, centered, font in blocks:
        if content is None:
            rows.append((None, False, None, height + 7))
            height += 16
            continue
        line = ""
        steps = []
        for word in content.split():
            candidate = (line + " " + word).strip()
            if line and font.getlength(candidate) > width - 2 * margin:
                steps.append(line)
                line = ""
            while font.getlength(word) > width - 2 * margin:
                end = 1
                while font.getlength(word[:end + 1]) <= width - 2 * margin:
                    end += 1
                steps.append(word[:end])
                word = word[end:]
            line = (line + " " + word).strip()
        if line:
            steps.append(line)
        for line in steps:
            rows.append((line, centered, font, height))
            height += sum(font.getmetrics()) + 4
        height += 5
        if height > 16000:
            raise ValueError("Nota longa demais para enviar como imagem.")

    image = Image.new("L", (width, height + margin), 255)
    draw = ImageDraw.Draw(image)
    for line, centered, font, y in rows:
        if line is None:
            draw.line((margin, y, width - margin, y), fill=0, width=2)
        else:
            x = (width - font.getlength(line)) / 2 if centered else margin
            draw.text((x, y), line, font=font, fill=0, anchor="lt")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _upload_receipt(code, text):
    png = _receipt_png(text)
    boundary = uuid4().hex
    data = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="pedido.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode("ascii") + png + f"\r\n--{boundary}--\r\n".encode("ascii")
    request = Request(
        f"https://printbridge.bluetoothprinter.in/api/v1/print-from-anywhere/{code}/attachments",
        data=data,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urlopen(request, timeout=8) as response:
        result = json.loads(response.read(65537))
    url = result.get("downloadUrl") if isinstance(result, dict) else None
    if not isinstance(url, str) or urlsplit(url).scheme != "https" or not urlsplit(url).hostname:
        raise ValueError("O serviço não devolveu o endereço da nota.")
    return {"imageUrl": url, "mimeType": "image/png"}


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
        }
        try:
            job["image"] = _upload_receipt(code, text)
        except (URLError, TimeoutError, OSError, ValueError):
            # Somente o anexo falhou: nenhum job de impressão foi enviado ainda.
            job.update(richText=_large_receipt_lines(text), strictMode=True, paperWidthMm=58)
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
