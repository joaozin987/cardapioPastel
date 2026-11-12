from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps
from hmac import compare_digest
from io import BytesIO
import json
import unicodedata
import os
from secrets import token_hex, token_urlsafe
from uuid import uuid4
from flask import Flask, jsonify, request, send_file, session
from PIL import Image, ImageOps, UnidentifiedImageError
from dotenv import load_dotenv
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix
import database
from database import get_connection, init_db

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
app = Flask(__name__)
# Atrás do proxy do Railway: lê o IP real do cliente (X-Forwarded-For).
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
PAGE_PATH = BASE_DIR / "da-lanches-pedidos.html"
secret_key = os.environ.get("FLASK_SECRET_KEY")
if not secret_key or secret_key.startswith("replace-with-"):
    secret_key = token_hex(32)
app.config.update(
    SECRET_KEY=secret_key,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "").lower() == "true",
)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
init_db()

def configured_profiles():
    return {
        "employee": (
            "station-1",
            "Funcionário",
            os.environ.get("STATION_1_PIN") or os.environ.get("EMPLOYEE_PIN"),
            "station",
        ),
        "admin": (
            "station-2",
            "Administrador",
            os.environ.get("ADMIN_PASSWORD")
            or os.environ.get("STATION_2_PIN")
            or os.environ.get("ADMIN_PIN"),
            "admin",
        ),
    }


PROFILES = configured_profiles()


def require_roles(*roles):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            current_role = session.get("role")
            if not current_role:
                return jsonify({"erro": "Faça login para continuar."}), 401
            if current_role not in roles:
                return jsonify({"erro": "Você não tem permissão para esta ação."}), 403
            return view(*args, **kwargs)

        return wrapped

    return decorate


staff_required = require_roles("admin", "station")
admin_required = require_roles("admin")
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_DURATION = timedelta(minutes=5)


def login_is_locked(account, ip_address):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT locked_until FROM auth_login_failures "
            "WHERE account=? AND ip_address=?",
            (account, ip_address),
        ).fetchone()
        return bool(
            row
            and row["locked_until"]
            and datetime.fromisoformat(row["locked_until"]) > datetime.now()
        )
    finally:
        conn.close()


def record_login_failure(account, ip_address):
    now = datetime.now()
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT attempts,window_started_at,locked_until FROM auth_login_failures "
            "WHERE account=? AND ip_address=?",
            (account, ip_address),
        ).fetchone()
        if row and row["locked_until"]:
            locked_until = datetime.fromisoformat(row["locked_until"])
            if locked_until > now:
                conn.commit()
                return True

        if not row or datetime.fromisoformat(row["window_started_at"]) < now - LOGIN_LOCKOUT_DURATION:
            attempts = 0
            window_started_at = now
        else:
            attempts = row["attempts"]
            window_started_at = datetime.fromisoformat(row["window_started_at"])
        attempts += 1
        locked_until = (
            now + LOGIN_LOCKOUT_DURATION if attempts >= LOGIN_MAX_ATTEMPTS else None
        )
        conn.execute(
            "INSERT OR REPLACE INTO auth_login_failures "
            "(account,ip_address,attempts,window_started_at,locked_until) "
            "VALUES(?,?,?,?,?)",
            (
                account,
                ip_address,
                attempts,
                window_started_at.isoformat(timespec="seconds"),
                locked_until.isoformat(timespec="seconds") if locked_until else None,
            ),
        )
        conn.commit()
        return locked_until is not None
    finally:
        conn.close()


def clear_login_failures(account, ip_address):
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM auth_login_failures WHERE account=? AND ip_address=?",
            (account, ip_address),
        )
        conn.commit()
    finally:
        conn.close()


@app.before_request
def verify_csrf_token():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and session.get("role"):
        expected = session.get("csrf_token", "")
        supplied = request.headers.get("X-CSRF-Token", "")
        if not expected or not compare_digest(expected, supplied):
            return jsonify({"erro": "Sessão expirada ou token de segurança inválido."}), 403


@app.get("/api/auth/session")
def auth_session():
    if session.get("role") == "station":
        if session.get("station_id") == "station-2":
            session["role"] = "admin"
            session["station_name"] = "Administrador"
        elif session.get("station_id") == "station-1":
            session["station_name"] = "Funcionário"
    elif session.get("role") == "admin" and not session.get("station_id"):
        session["station_id"] = "station-2"
        session["station_name"] = "Administrador"

    csrf_token = session.setdefault("csrf_token", token_urlsafe(32))
    return jsonify({
        "authenticated": bool(session.get("role")),
        "role": session.get("role"),
        "station_id": session.get("station_id"),
        "station_name": session.get("station_name"),
        "csrf_token": csrf_token,
    })


@app.post("/api/auth/login")
def auth_login():
    data = request.get_json(silent=True) or {}
    account = data.get("account")
    credential = data.get("credential")
    if (
        not isinstance(account, str)
        or not isinstance(credential, str)
        or not credential
        or len(credential) > 256
    ):
        return jsonify({"erro": "Informe a senha ou o PIN."}), 400

    profile = PROFILES.get(account)
    if not profile:
        return jsonify({"erro": "Acesso inválido."}), 401
    station_id, station_name, expected, role = profile

    if not expected or expected.startswith("replace-with-"):
        app.logger.error("Credencial local não configurada para a conta %s", account)
        return jsonify({"erro": "Esta conta ainda não foi configurada no servidor."}), 503
    ip_address = request.remote_addr or "unknown"
    if login_is_locked(account, ip_address):
        return jsonify({"erro": "Muitas tentativas. Aguarde 5 minutos e tente novamente."}), 429
    if not compare_digest(expected, credential):
        if record_login_failure(account, ip_address):
            return jsonify({"erro": "Muitas tentativas. Aguarde 5 minutos e tente novamente."}), 429
        return jsonify({"erro": "Senha ou PIN incorreto."}), 401

    clear_login_failures(account, ip_address)
    csrf_token = session.get("csrf_token") or token_urlsafe(32)
    session.clear()
    session.update(
        role=role,
        station_id=station_id,
        station_name=station_name,
        csrf_token=csrf_token,
    )
    return jsonify({
        "authenticated": True,
        "role": role,
        "station_id": station_id,
        "station_name": station_name,
        "csrf_token": csrf_token,
    })


@app.post("/api/auth/logout")
@staff_required
def auth_logout():
    session.clear()
    return jsonify({"ok": True})


def produto_dict(row):
    return {"id": row["id"], "c": row["categoria"], "n": row["nome"], "d": row["descricao"] or "",
            "p": float(row["preco"]) if row["preco_definido"] else None,
            "e": row["estoque"], "on": bool(row["ativo"]),
            "img": f"/api/produtos/{row['id']}/imagem?v={row['imagem']}" if row["imagem"] else None,
            "updated": row["atualizado_em"]}

def process_product_image(upload):
    if upload is None:
        return None

    try:
        raw = upload.read()
        with Image.open(BytesIO(raw)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Use uma imagem JPG, PNG ou WEBP.")
            if source.width * source.height > 40_000_000:
                raise ValueError("A imagem tem resolução muito alta.")
            source.load()
            oriented = ImageOps.exif_transpose(source).convert("RGB")
            for size in (600, 500, 400, 320):
                square = ImageOps.fit(
                    oriented,
                    (size, size),
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.5),
                )
                for quality in (82, 74, 66, 58):
                    output = BytesIO()
                    square.save(output, format="JPEG", quality=quality, optimize=True)
                    if output.tell() <= 200 * 1024:
                        return output.getvalue()
            raise ValueError("Não foi possível reduzir a imagem abaixo de 200 KB.")
    except ValueError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("O arquivo selecionado não é uma imagem válida.") from error

@app.errorhandler(RequestEntityTooLarge)
def request_too_large(_error):
    return jsonify({"erro": "A imagem deve ter no máximo 5 MB."}), 413

def carregar_pedido(conn, pedido):
    itens = conn.execute("SELECT id,produto_id,nome_produto,quantidade,preco_unitario,pronto FROM pedido_itens WHERE pedido_id=? ORDER BY id", (pedido["id"],)).fetchall()
    tipo = pedido["tipo"]
    mesa = f"{tipo} {pedido['numero']}" if pedido["numero"] is not None else tipo
    return {"id": pedido["id"], "mesa": mesa, "obs": pedido["observacao"] or "", "junto": bool(pedido["entregar_junto"]),
            "cancel": bool(pedido["cancelado"]), "pronto": pedido["status"] == "pronto", "t": pedido["data_criacao"],
            "estacao_id": pedido["estacao_id"], "impressao_status": pedido["impressao_status"],
            "itens": [{"produto_id": x["produto_id"], "n": x["nome_produto"], "q": x["quantidade"], "p": float(x["preco_unitario"]), "ok": bool(x["pronto"])} for x in itens]}

@app.get("/")
def home():
    return send_file(PAGE_PATH)

@app.get("/api/dados")
@staff_required
def dados():
    conn = get_connection()
    try:
        produtos = conn.execute("SELECT p.*,c.nome AS categoria FROM produtos p JOIN categorias c ON c.id=p.categoria_id ORDER BY p.atualizado_em,p.id").fetchall()
        pedidos = conn.execute("SELECT * FROM pedidos ORDER BY id DESC").fetchall()
        return jsonify({"produtos": [produto_dict(p) for p in produtos], "pedidos": [carregar_pedido(conn, p) for p in pedidos]})
    finally:
        conn.close()

@app.get("/api/produtos/<int:product_id>/imagem")
@staff_required
def imagem_produto(product_id):
    conn = get_connection()
    try:
        row = conn.execute("SELECT imagem FROM produtos WHERE id=?", (product_id,)).fetchone()
        if not row or not row["imagem"]:
            return jsonify({"erro": "Imagem do produto não encontrada."}), 404
        image_path = database_image_directory() / row["imagem"]
        if not image_path.is_file():
            return jsonify({"erro": "Arquivo de imagem não encontrado."}), 404
        return send_file(image_path, mimetype="image/jpeg", conditional=True, max_age=86400)
    finally:
        conn.close()

def database_image_directory():
    return database.DB_PATH.parent / "product_images"

def printer_ascii(value):
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return normalized.encode("ascii", "ignore").decode("ascii")


def build_print_payload(conn, pedido_id):
    pedido = conn.execute("SELECT * FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
    itens = conn.execute(
        "SELECT nome_produto,quantidade,preco_unitario FROM pedido_itens WHERE pedido_id=? ORDER BY id",
        (pedido_id,),
    ).fetchall()
    mesa = f"{pedido['tipo']} {pedido['numero']}" if pedido["numero"] is not None else pedido["tipo"]
    return {"pedido_id": pedido_id, "mesa": printer_ascii(mesa), "observacao": printer_ascii(pedido["observacao"] or ""),
            "criado_em": pedido["data_criacao"],
            "itens": [{"nome": printer_ascii(x["nome_produto"]), "quantidade": x["quantidade"],
                       "preco": float(x["preco_unitario"])} for x in itens]}


def enqueue_print_job(conn, pedido_id, station_id):
    now = datetime.now().isoformat(timespec="seconds")
    payload = build_print_payload(conn, pedido_id)
    conn.execute(
        "INSERT INTO print_jobs(pedido_id,station_id,payload,status,created_at,updated_at) "
        "VALUES(?,?,?,'pendente',?,?)",
        (pedido_id, station_id, json.dumps(payload, ensure_ascii=False), now, now),
    )
    conn.execute("UPDATE pedidos SET impressao_status='pendente',impressao_atualizada_em=? WHERE id=?",
                 (now, pedido_id))


def require_print_agent():
    expected = os.environ.get("PRINT_AGENT_TOKEN", "")
    supplied = request.headers.get("X-Print-Agent-Token", "")
    if not expected or expected.startswith("replace-with-"):
        return jsonify({"erro": "A ponte de impressão ainda não foi configurada no servidor."}), 503
    if not supplied or not compare_digest(expected, supplied):
        return jsonify({"erro": "Credencial da ponte inválida."}), 401
    return None


@app.post("/api/pedidos")
@require_roles("station", "admin")
def criar_pedido():
    data = request.get_json(silent=True) or {}
    itens = data.get("itens")
    if not isinstance(itens, list) or not itens:
        return jsonify({"erro": "Adicione pelo menos um produto ao pedido."}), 400
    mesa = str(data.get("mesa", "Balcão")).strip()
    if mesa.startswith("Mesa "):
        tipo, numero = "Mesa", mesa[5:]
    elif mesa.startswith("Ficha "):
        tipo, numero = "Ficha", mesa[6:]
    else:
        tipo, numero = "Balcão", None
    if tipo != "Balcão":
        try: numero = int(numero)
        except (TypeError, ValueError): return jsonify({"erro": "Número de mesa/ficha inválido."}), 400
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        validos = []
        for item in itens:
            try: pid, qtd = int(item.get("id")), int(item.get("q"))
            except (TypeError, ValueError, AttributeError): raise ValueError("Item inválido no pedido.")
            if qtd < 1: raise ValueError("A quantidade precisa ser maior que zero.")
            p = conn.execute("SELECT * FROM produtos WHERE id=? AND ativo=1", (pid,)).fetchone()
            if not p: raise ValueError("Um produto não está mais disponível. Atualize o cardápio.")
            if not p["preco_definido"]:
                raise ValueError(f"Defina o preço de {p['nome']} antes de vender.")
            if p["estoque"] is not None and p["estoque"] < qtd:
                raise ValueError(f"Estoque insuficiente para {p['nome']}. Disponível: {p['estoque']}.")
            validos.append((p, qtd))
        cur = conn.execute("INSERT INTO pedidos(tipo,numero,observacao,entregar_junto,status,data_criacao,estacao_id) VALUES(?,?,?,?,?,?,?)",
                           (tipo, numero, str(data.get("obs", ""))[:500], int(bool(data.get("junto"))), "em_preparo", datetime.now().isoformat(timespec="seconds"), session["station_id"]))
        pedido_id = cur.lastrowid
        for p, qtd in validos:
            conn.execute("INSERT INTO pedido_itens(pedido_id,produto_id,nome_produto,quantidade,preco_unitario) VALUES(?,?,?,?,?)",
                         (pedido_id, p["id"], p["nome"], qtd, p["preco"]))
            if p["estoque"] is not None:
                conn.execute("UPDATE produtos SET estoque=estoque-? WHERE id=?", (qtd, p["id"]))
        enqueue_print_job(conn, pedido_id, session["station_id"])
        conn.commit()
        pedido = conn.execute("SELECT * FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        return jsonify({"pedido": carregar_pedido(conn, pedido)}), 201
    except ValueError as e:
        conn.rollback(); return jsonify({"erro": str(e)}), 400
    except Exception:
        conn.rollback(); app.logger.exception("Falha ao criar pedido")
        return jsonify({"erro": "Não foi possível salvar o pedido."}), 500
    finally: conn.close()

@app.route("/api/produtos", methods=["GET", "POST", "PUT"])
@staff_required
def salvar_produto():
    if request.method == "GET":
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT p.*,c.nome AS categoria FROM produtos p "
                "JOIN categorias c ON c.id=p.categoria_id ORDER BY p.atualizado_em,p.id"
            ).fetchall()
            return jsonify({"produtos": [produto_dict(row) for row in rows]})
        finally:
            conn.close()
    if session.get("role") != "admin":
        return jsonify({"erro": "Somente o administrador pode alterar produtos."}), 403

    data = (request.get_json(silent=True) or {}) if request.is_json else request.form.to_dict()
    image_upload = request.files.get("image")
    try:
        image_bytes = process_product_image(image_upload) if image_upload and image_upload.filename else None
    except ValueError as error:
        return jsonify({"erro": str(error)}), 400
    remove_image = data.get("remove_image") == "true"
    try:
        nome = str(data.get("n", "")).strip(); categoria = str(data.get("c", "")).strip()
        descricao = str(data.get("d", "")).strip()
        preco_informado = data.get("p") not in (None, "")
        preco = float(data["p"]) if preco_informado else 0
        estoque = data.get("e")
        estoque = None if estoque in (None, "") else int(estoque)
        ativo_value = data.get("on", True)
        ativo = int(
            ativo_value
            if isinstance(ativo_value, bool)
            else str(ativo_value).lower() in {"1", "true", "on"}
        )
        if not nome or not categoria or preco < 0 or (estoque is not None and estoque < 0): raise ValueError()
    except (TypeError, ValueError): return jsonify({"erro": "Confira nome, categoria, preço e estoque."}), 400
    conn = get_connection()
    image_name = None
    old_image_name = None
    written_image_path = None
    committed = False
    try:
        conn.execute("INSERT OR IGNORE INTO categorias(nome) VALUES(?)", (categoria,))
        cid = conn.execute("SELECT id FROM categorias WHERE nome=?", (categoria,)).fetchone()[0]
        if request.method == "PUT":
            pid = int(data.get("id"))
            existing = conn.execute("SELECT imagem FROM produtos WHERE id=?", (pid,)).fetchone()
            if not existing:
                return jsonify({"erro":"Produto não encontrado."}), 404
            old_image_name = existing["imagem"]
            image_name = None if remove_image else old_image_name
            if image_bytes:
                image_name = f"{uuid4().hex}.jpg"
            cur = conn.execute("UPDATE produtos SET categoria_id=?,nome=?,descricao=?,preco=?,preco_definido=?,estoque=?,ativo=?,imagem=?,atualizado_em=? WHERE id=?", (cid,nome,descricao,preco,int(preco_informado),estoque,ativo,image_name,datetime.now().isoformat(timespec="microseconds"),pid))
            if not cur.rowcount: return jsonify({"erro":"Produto não encontrado."}), 404
        else:
            image_name = f"{uuid4().hex}.jpg" if image_bytes else None
            cur = conn.execute("INSERT INTO produtos(categoria_id,nome,descricao,preco,preco_definido,estoque,ativo,imagem,atualizado_em) VALUES(?,?,?,?,?,?,?,?,?)", (cid,nome,descricao,preco,int(preco_informado),estoque,ativo,image_name,datetime.now().isoformat(timespec="microseconds")))
            pid = cur.lastrowid
        if image_bytes:
            image_directory = database_image_directory()
            image_directory.mkdir(parents=True, exist_ok=True)
            written_image_path = image_directory / image_name
            written_image_path.write_bytes(image_bytes)
        row = conn.execute("SELECT p.*,c.nome categoria FROM produtos p JOIN categorias c ON c.id=p.categoria_id WHERE p.id=?", (pid,)).fetchone()
        conn.commit()
        committed = True
        response = jsonify({"produto":produto_dict(row)})
        if old_image_name and old_image_name != image_name:
            old_path = database_image_directory() / old_image_name
            try:
                if old_path.exists():
                    old_path.unlink()
            except OSError:
                app.logger.exception("Falha ao remover imagem antiga do produto %s", pid)
        return response
    except Exception:
        conn.rollback()
        if written_image_path and not committed and written_image_path.exists():
            try:
                written_image_path.unlink()
            except OSError:
                app.logger.exception("Falha ao remover imagem incompleta do produto %s", pid)
        app.logger.exception("Falha ao salvar produto")
        return jsonify({"erro":"Não foi possível salvar o produto."}),500
    finally: conn.close()


@app.get("/api/admin/resumo")
@admin_required
def admin_summary():
    conn = get_connection()
    try:
        today = datetime.now().date().isoformat()
        totals = conn.execute(
            "SELECT COUNT(*) AS pedidos, COALESCE(SUM("
            "(SELECT SUM(pi.quantidade * pi.preco_unitario) FROM pedido_itens pi "
            "WHERE pi.pedido_id=p.id)), 0) AS vendas "
            "FROM pedidos p WHERE date(p.data_criacao)=date(?) AND p.cancelado=0",
            (today,),
        ).fetchone()
        products = conn.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN ativo=1 THEN 1 ELSE 0 END) AS ativos "
            "FROM produtos"
        ).fetchone()
        printing = conn.execute(
            "SELECT impressao_status, COUNT(*) AS quantidade FROM pedidos "
            "WHERE date(data_criacao)=date(?) GROUP BY impressao_status",
            (today,),
        ).fetchall()
        return jsonify({
            "pedidos_hoje": totals["pedidos"],
            "vendas_hoje": float(totals["vendas"]),
            "produtos_total": products["total"],
            "produtos_ativos": products["ativos"] or 0,
            "impressao_hoje": {row["impressao_status"]: row["quantidade"] for row in printing},
            "estacoes": [
                {
                    "id": station_id,
                    "nome": name,
                    "configurada": bool(pin and not pin.startswith("replace-with-")),
                }
                for station_id, name, pin, _role in PROFILES.values()
            ],
        })
    finally:
        conn.close()


@app.post("/api/pedidos/<int:pedido_id>/impressao")
@require_roles("station", "admin")
def atualizar_impressao(pedido_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in {"imprimindo", "impresso", "falhou"}:
        return jsonify({"erro": "Estado de impressão inválido."}), 400

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        pedido = conn.execute(
            "SELECT estacao_id,impressao_status FROM pedidos WHERE id=?", (pedido_id,)
        ).fetchone()
        if not pedido:
            return jsonify({"erro": "Pedido não encontrado."}), 404
        if pedido["estacao_id"] != session["station_id"]:
            return jsonify({"erro": "Este pedido pertence a outra estação."}), 403

        allowed_from = {
            "imprimindo": {"pendente"},
            "impresso": {"imprimindo"},
            "falhou": {"imprimindo"},
        }
        if pedido["impressao_status"] not in allowed_from[status]:
            return jsonify({"erro": "Este pedido já iniciou ou concluiu a impressão."}), 409
        conn.execute(
            "UPDATE pedidos SET impressao_status=?,impressao_atualizada_em=? WHERE id=?",
            (status, datetime.now().isoformat(timespec="seconds"), pedido_id),
        )
        conn.commit()
        return jsonify({"ok": True, "status": status})
    finally:
        conn.close()


@app.post("/api/pedidos/<int:pedido_id>/reimprimir")
@require_roles("station", "admin")
def reimprimir_pedido(pedido_id):
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        pedido = conn.execute("SELECT estacao_id FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        if not pedido:
            return jsonify({"erro": "Pedido não encontrado."}), 404
        if pedido["estacao_id"] != session["station_id"]:
            return jsonify({"erro": "Este pedido pertence a outra estação."}), 403
        enqueue_print_job(conn, pedido_id, session["station_id"])
        conn.commit()
        return jsonify({"ok": True, "status": "pendente"}), 202
    except Exception:
        conn.rollback()
        app.logger.exception("Falha ao colocar reimpressão na fila")
        return jsonify({"erro": "Não foi possível colocar o pedido na fila de impressão."}), 500
    finally:
        conn.close()


@app.get("/api/print-agent/jobs/next")
def print_agent_next_job():
    auth_error = require_print_agent()
    if auth_error: return auth_error
    station_id = request.args.get("station_id", "")
    agent_id = request.headers.get("X-Print-Agent-Id", "esp32")
    if station_id not in {profile[0] for profile in PROFILES.values()}:
        return jsonify({"erro": "Estação inválida."}), 400
    if not agent_id or len(agent_id) > 80:
        return jsonify({"erro": "Identificação da ponte inválida."}), 400
    now = datetime.now()
    now_text = now.isoformat(timespec="seconds")
    lease_text = (now + timedelta(seconds=90)).isoformat(timespec="seconds")
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO print_agent_heartbeats(station_id,agent_id,last_seen,printer_name) "
            "VALUES(?,?,?,NULL) ON CONFLICT(station_id) DO UPDATE SET "
            "agent_id=excluded.agent_id,last_seen=excluded.last_seen",
            (station_id, agent_id, now_text),
        )
        expired = conn.execute(
            "SELECT id,pedido_id FROM print_jobs WHERE station_id=? AND status='processando' "
            "AND lease_until<? AND attempts>=5",
            (station_id, now_text),
        ).fetchall()
        for expired_job in expired:
            conn.execute(
                "UPDATE print_jobs SET status='falhou',last_error='Tempo limite da ponte excedido.',"
                "claimed_by=NULL,lease_until=NULL,updated_at=? WHERE id=?",
                (now_text, expired_job["id"]),
            )
            conn.execute(
                "UPDATE pedidos SET impressao_status='falhou',impressao_atualizada_em=? WHERE id=?",
                (now_text, expired_job["pedido_id"]),
            )
        job = conn.execute(
            "SELECT * FROM print_jobs WHERE station_id=? AND attempts<5 AND "
            "(status='pendente' OR (status='processando' AND lease_until<?)) "
            "ORDER BY created_at,id LIMIT 1", (station_id, now_text),
        ).fetchone()
        if not job:
            conn.commit()
            return jsonify({"job": None, "poll_after_seconds": 3})
        conn.execute(
            "UPDATE print_jobs SET status='processando',attempts=attempts+1,claimed_by=?,lease_until=?,updated_at=? WHERE id=?",
            (agent_id, lease_text, now_text, job["id"]),
        )
        conn.execute(
            "UPDATE pedidos SET impressao_status='imprimindo',impressao_atualizada_em=? WHERE id=?",
            (now_text, job["pedido_id"]),
        )
        conn.commit()
        return jsonify({"job": {"id": job["id"], "pedido_id": job["pedido_id"],
                                "attempt": job["attempts"] + 1, "payload": json.loads(job["payload"])},
                        "lease_seconds": 90})
    except Exception:
        conn.rollback()
        app.logger.exception("Falha ao reservar trabalho de impressão")
        return jsonify({"erro": "Não foi possível consultar a fila."}), 500
    finally:
        conn.close()


@app.post("/api/print-agent/jobs/<int:job_id>/result")
def print_agent_job_result(job_id):
    auth_error = require_print_agent()
    if auth_error: return auth_error
    data = request.get_json(silent=True) or {}
    station_id = data.get("station_id")
    agent_id = request.headers.get("X-Print-Agent-Id", "esp32")
    success = data.get("success")
    error_message = str(data.get("error", ""))[:500]
    if success not in (True, False):
        return jsonify({"erro": "Informe success como booleano."}), 400
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        job = conn.execute(
            "SELECT pedido_id,station_id,status,attempts,claimed_by FROM print_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if not job: return jsonify({"erro": "Trabalho de impressão não encontrado."}), 404
        if job["station_id"] != station_id:
            return jsonify({"erro": "Trabalho pertence a outra estação."}), 403
        if job["status"] != "processando" or job["claimed_by"] != agent_id:
            return jsonify({"erro": "A reserva expirou ou pertence a outra ponte."}), 409
        if success: job_status = order_status = "impresso"
        elif job["attempts"] >= 5: job_status = order_status = "falhou"
        else: job_status = order_status = "pendente"
        conn.execute(
            "UPDATE print_jobs SET status=?,last_error=?,claimed_by=NULL,lease_until=NULL,updated_at=? WHERE id=?",
            (job_status, None if success else error_message or "Falha informada pela ponte.", now, job_id),
        )
        conn.execute("UPDATE pedidos SET impressao_status=?,impressao_atualizada_em=? WHERE id=?",
                     (order_status, now, job["pedido_id"]))
        conn.commit()
        return jsonify({"ok": True, "status": order_status, "will_retry": order_status == "pendente"})
    except Exception:
        conn.rollback()
        app.logger.exception("Falha ao registrar resultado da impressão")
        return jsonify({"erro": "Não foi possível registrar o resultado."}), 500
    finally:
        conn.close()


@app.get("/api/print-agent/status")
def print_agent_status():
    auth_error = require_print_agent()
    if auth_error: return auth_error
    station_id = request.args.get("station_id", "")
    conn = get_connection()
    try:
        row = conn.execute("SELECT agent_id,last_seen FROM print_agent_heartbeats WHERE station_id=?",
                           (station_id,)).fetchone()
        online = bool(row and datetime.fromisoformat(row["last_seen"]) >= datetime.now()-timedelta(seconds=20))
        return jsonify({"online": online, "last_seen": row["last_seen"] if row else None})
    finally:
        conn.close()


@app.patch("/api/pedidos/<int:pedido_id>/itens/<int:item_index>")
@staff_required
def marcar_item(pedido_id, item_index):
    data=request.get_json(silent=True) or {}; pronto=int(bool(data.get("pronto")))
    conn=get_connection()
    try:
        row=conn.execute("SELECT id FROM pedido_itens WHERE pedido_id=? ORDER BY id LIMIT 1 OFFSET ?",(pedido_id,item_index)).fetchone()
        pedido=conn.execute("SELECT cancelado,status FROM pedidos WHERE id=?",(pedido_id,)).fetchone()
        if not row or not pedido: return jsonify({"erro":"Pedido ou item não encontrado."}),404
        if pedido["cancelado"] or pedido["status"]=="pronto": return jsonify({"erro":"Este pedido já foi encerrado."}),409
        conn.execute("UPDATE pedido_itens SET pronto=? WHERE id=?",(pronto,row["id"]))
        conn.commit(); return jsonify({"ok":True})
    finally: conn.close()

@app.patch("/api/pedidos/<int:pedido_id>/pronto")
@staff_required
def concluir_pedido(pedido_id):
    conn=get_connection()
    try:
        cur=conn.execute("UPDATE pedidos SET status='pronto' WHERE id=? AND cancelado=0",(pedido_id,))
        if not cur.rowcount: return jsonify({"erro":"Pedido não encontrado ou cancelado."}),404
        conn.execute("UPDATE pedido_itens SET pronto=1 WHERE pedido_id=?",(pedido_id,)); conn.commit()
        return jsonify({"ok":True})
    finally: conn.close()

@app.post("/api/pedidos/<int:pedido_id>/cancelar")
@staff_required
def cancelar_pedido(pedido_id):
    conn=get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        pedido=conn.execute("SELECT cancelado FROM pedidos WHERE id=?",(pedido_id,)).fetchone()
        if not pedido: return jsonify({"erro":"Pedido não encontrado."}),404
        if not pedido["cancelado"]:
            itens=conn.execute("SELECT produto_id,quantidade FROM pedido_itens WHERE pedido_id=?",(pedido_id,)).fetchall()
            for item in itens:
                if item["produto_id"] is not None:
                    conn.execute("UPDATE produtos SET estoque=estoque+? WHERE id=? AND estoque IS NOT NULL",(item["quantidade"],item["produto_id"]))
            conn.execute("UPDATE pedidos SET cancelado=1,status='cancelado' WHERE id=?",(pedido_id,))
        conn.commit(); return jsonify({"ok":True})
    except Exception:
        conn.rollback(); app.logger.exception("Falha ao cancelar pedido"); return jsonify({"erro":"Não foi possível cancelar o pedido."}),500
    finally: conn.close()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "true").lower() == "true",
    )