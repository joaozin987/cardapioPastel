from pathlib import Path
import base64
import gzip
import os
from contextlib import closing
import sqlite3
from tempfile import NamedTemporaryFile

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or BASE_DIR / "instance")
DB_PATH = Path(os.environ.get("DATABASE_PATH") or DATA_DIR / "da_lanches.db")


MENU_INICIAL = {
    "Pastéis": [("Pastel de queijo", 9, "Massa crocante com queijo derretido"), ("Pastel misto", 9, "Queijo e presunto"), ("Pastel de carne de sol com queijo", 9, "Carne de sol desfiada com queijo"), ("Pastel de frango com catupiry", 9, "Frango desfiado com catupiry cremoso"), ("Pastel de frango com queijo", 9, "Frango desfiado com queijo"), ("Pastel de calabresa com queijo", 9, "Calabresa fatiada com queijo")],
    "Coxinhas": [("Coxinha de frango", 7, "Massa macia recheada com frango desfiado")],
    "Pizzas": [("Pizza brotinho de calabresa", 10, "Brotinho com mussarela e calabresa"), ("Pizza brotinho de mussarela", 10, "Brotinho com molho e mussarela"), ("Pizza brotinho de frango com catupiry", 10, "Brotinho com frango e catupiry")],
    "Bebidas": [("Guaraná Pitulinha 200 ml", 4, "Garrafinha de 200 ml"), ("Coca-Cola lata", 6, "Lata gelada"), ("Suco natural", 8, "Copo, sabor do dia")]
}
ESTOQUE_INICIAL = {"Pastéis": 30, "Coxinhas": 20, "Pizzas": 10, "Bebidas": 24}
PRODUTOS_ADICIONAIS = {
    "Pastéis": [
        ("Pastel mistão", "Pastel misto especial"),
        ("Pastel de frango", "Pastel recheado com frango"),
        ("Pastel de carne", "Pastel recheado com carne")
    ],
    "Coxinhas": [
        ("Coxinha de frango com catupiry", "Coxinha recheada com frango e catupiry"),
        ("Coxinha de costela", "Coxinha recheada com costela"),
        ("Coxinha de frango com bacon", "Coxinha recheada com frango e bacon")
    ],
    "Caldos": [
        ("Caldo 400 ml", "Caldo na porção de 400 ml"),
        ("Caldo 500 ml", "Caldo na porção de 500 ml"),
        ("Caldo 770 ml", "Caldo na porção de 770 ml")
    ],
    "Lasanhas": [
        ("Lasanha de frango", "Lasanha de frango"),
        ("Lasanha de carne", "Lasanha de carne")
    ]
}
CATALOG_UPDATE_VERSION = 1

def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn

def init_db():
    # Na migração para o volume, restaura somente quando ainda não existe banco.
    snapshot = os.environ.get("DATABASE_INITIAL_SNAPSHOT")
    if not DB_PATH.exists() and snapshot:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=DB_PATH.parent, suffix=".db", delete=False) as temp:
            temp_path = Path(temp.name)
            temp.write(gzip.decompress(base64.b64decode(snapshot, validate=True)))
        try:
            with closing(sqlite3.connect(temp_path)) as restored:
                if restored.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("A cópia inicial do banco está inválida.")
            os.replace(temp_path, DB_PATH)
        finally:
            temp_path.unlink(missing_ok=True)
    conn = get_connection()
    try:
        order_columns = {row["name"] for row in conn.execute("PRAGMA table_info(pedidos)")}
        if order_columns and "impressao_destino" not in order_columns:
            conn.execute("BEGIN IMMEDIATE")
            order_columns = {row["name"] for row in conn.execute("PRAGMA table_info(pedidos)")}
            if "impressao_destino" not in order_columns:
                with NamedTemporaryFile(prefix=f"{DB_PATH.stem}.before-impressao-destino-",
                                        suffix=".db", dir=DB_PATH.parent, delete=False) as backup_file:
                    backup_path = Path(backup_file.name)
                try:
                    # Outra conexão lê o snapshot enquanto esta impede novas escritas.
                    with closing(sqlite3.connect(DB_PATH)) as source, closing(sqlite3.connect(backup_path)) as backup:
                        source.backup(backup)
                except Exception:
                    backup_path.unlink(missing_ok=True)
                    raise
                conn.execute(
                    "ALTER TABLE pedidos ADD COLUMN impressao_destino TEXT NOT NULL DEFAULT 'simple_bluetooth' "
                    "CHECK(impressao_destino IN ('padrao','simple_bluetooth','web_bluetooth','airprint'))"
                )
            conn.commit()
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            descricao TEXT DEFAULT '',
            preco REAL NOT NULL CHECK(preco >= 0),
            preco_definido INTEGER NOT NULL DEFAULT 1 CHECK(preco_definido IN (0, 1)),
            estoque INTEGER NULL CHECK(estoque IS NULL OR estoque >= 0),
            ativo INTEGER NOT NULL DEFAULT 1,
            atualizado_em TEXT,
            FOREIGN KEY(categoria_id) REFERENCES categorias(id)
        );
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            numero INTEGER NULL,
            observacao TEXT DEFAULT '',
            entregar_junto INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'em_preparo',
            cancelado INTEGER NOT NULL DEFAULT 0,
            data_criacao TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            estacao_id TEXT NOT NULL DEFAULT 'station-1',
            impressao_destino TEXT NOT NULL DEFAULT 'simple_bluetooth'
                CHECK(impressao_destino IN ('padrao','simple_bluetooth','web_bluetooth','airprint')),
            impressao_status TEXT NOT NULL DEFAULT 'pendente',
            impressao_atualizada_em TEXT
        );
        CREATE TABLE IF NOT EXISTS pedido_itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER NOT NULL,
            produto_id INTEGER NULL,
            nome_produto TEXT NOT NULL,
            quantidade INTEGER NOT NULL CHECK(quantidade > 0),
            preco_unitario REAL NOT NULL CHECK(preco_unitario >= 0),
            pronto INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE,
            FOREIGN KEY(produto_id) REFERENCES produtos(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS print_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER NOT NULL,
            station_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pendente'
                CHECK(status IN ('pendente','processando','impresso','falhou')),
            attempts INTEGER NOT NULL DEFAULT 0,
            claimed_by TEXT,
            lease_until TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY(pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_print_jobs_queue ON print_jobs(station_id,status,created_at);
        CREATE TABLE IF NOT EXISTS print_agent_heartbeats (
            station_id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            printer_name TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_pedidos_data ON pedidos(data_criacao);
        CREATE INDEX IF NOT EXISTS idx_itens_pedido ON pedido_itens(pedido_id);
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS auth_login_failures (
            account TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            attempts INTEGER NOT NULL,
            window_started_at TEXT NOT NULL,
            locked_until TEXT,
            PRIMARY KEY (account, ip_address)
        );
        """)
        product_columns = {row["name"] for row in conn.execute("PRAGMA table_info(produtos)")}
        if "preco_definido" not in product_columns:
            conn.execute("ALTER TABLE produtos ADD COLUMN preco_definido INTEGER NOT NULL DEFAULT 1")
        if "imagem" not in product_columns:
            conn.execute("ALTER TABLE produtos ADD COLUMN imagem TEXT")
        if "atualizado_em" not in product_columns:
            conn.execute("ALTER TABLE produtos ADD COLUMN atualizado_em TEXT")
        conn.execute(
            "UPDATE produtos SET atualizado_em=datetime('now','localtime') "
            "WHERE atualizado_em IS NULL"
        )
        order_columns = {row["name"] for row in conn.execute("PRAGMA table_info(pedidos)")}
        if "estacao_id" not in order_columns:
            conn.execute(
                "ALTER TABLE pedidos ADD COLUMN estacao_id TEXT NOT NULL DEFAULT 'station-1'"
            )
        if "impressao_status" not in order_columns:
            conn.execute(
                "ALTER TABLE pedidos ADD COLUMN impressao_status TEXT NOT NULL DEFAULT 'pendente'"
            )
        if "impressao_atualizada_em" not in order_columns:
            conn.execute("ALTER TABLE pedidos ADD COLUMN impressao_atualizada_em TEXT")

        # Popula somente banco vazio; nunca redefine estoque ou produtos existentes.
        if conn.execute("SELECT COUNT(*) FROM produtos").fetchone()[0] == 0:
            for categoria, itens in MENU_INICIAL.items():
                conn.execute("INSERT OR IGNORE INTO categorias(nome) VALUES (?)", (categoria,))
                cid = conn.execute("SELECT id FROM categorias WHERE nome=?", (categoria,)).fetchone()[0]
                for nome, preco, descricao in itens:
                    conn.execute("INSERT INTO produtos(categoria_id,nome,descricao,preco,preco_definido,estoque,ativo,atualizado_em) VALUES(?,?,?,?,1,?,1,datetime('now','localtime'))",
                                 (cid, nome, descricao, preco, ESTOQUE_INICIAL[categoria]))

        migration = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version=?",
            (CATALOG_UPDATE_VERSION,)
        ).fetchone()
        if not migration:
            for categoria, produtos in PRODUTOS_ADICIONAIS.items():
                conn.execute("INSERT OR IGNORE INTO categorias(nome) VALUES (?)", (categoria,))
                categoria_id = conn.execute(
                    "SELECT id FROM categorias WHERE nome=?",
                    (categoria,)
                ).fetchone()["id"]
                for nome, descricao in produtos:
                    exists = conn.execute(
                        "SELECT 1 FROM produtos WHERE categoria_id=? AND nome=?",
                        (categoria_id, nome)
                    ).fetchone()
                    if not exists:
                        conn.execute(
                            "INSERT INTO produtos(categoria_id,nome,descricao,preco,preco_definido,estoque,ativo,atualizado_em) "
                            "VALUES(?,?,?,0,0,NULL,1,datetime('now','localtime'))",
                            (categoria_id, nome, descricao)
                        )

            conn.execute(
                "UPDATE produtos SET preco=10,preco_definido=1 "
                "WHERE nome IN (?,?,?) AND categoria_id=(SELECT id FROM categorias WHERE nome='Pizzas')",
                ("Pizza brotinho de calabresa", "Pizza brotinho de mussarela", "Pizza brotinho de frango com catupiry")
            )
            conn.execute(
                "INSERT INTO schema_migrations(version) VALUES(?)",
                (CATALOG_UPDATE_VERSION,)
            )
        conn.commit()
    finally:
        conn.close()
