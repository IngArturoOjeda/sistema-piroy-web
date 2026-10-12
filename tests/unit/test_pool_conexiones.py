"""
Pool de conexiones a PostgreSQL: se crea una sola vez, la "conexion" que reciben los routers
devuelve la conexion al pool al cerrarse y delega el resto. Sin tocar ninguna base.
"""
import pytest
from psycopg.pq import TransactionStatus

from backend.app import database_postgres as db


class InfoFalsa:
    def __init__(self):
        self.transaction_status = TransactionStatus.IDLE


class ConexionFalsa:
    def __init__(self):
        self.eventos = []
        self.info = InfoFalsa()

    def cursor(self, *args, **kwargs):
        self.eventos.append(("cursor", args, kwargs))
        return "un-cursor"

    def commit(self):
        self.eventos.append("commit")

    def rollback(self):
        self.eventos.append("rollback")


class PoolFalso:
    check_connection = staticmethod(lambda conn: None)   # imita ConnectionPool.check_connection
    creados = []

    def __init__(self, conninfo, **kwargs):
        self.conninfo = conninfo
        self.kwargs = kwargs
        self.abierto = False
        self.devueltas = []
        self.prestada = ConexionFalsa()
        PoolFalso.creados.append(self)

    def open(self):
        self.abierto = True

    def getconn(self):
        return self.prestada

    def putconn(self, conexion):
        self.devueltas.append(conexion)


@pytest.fixture(autouse=True)
def pool_limpio(monkeypatch):
    PoolFalso.creados = []
    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setattr(db, "ConnectionPool", PoolFalso)
    monkeypatch.setattr(db, "DATABASE_URL", "postgresql://usuario:clave@servidor/base")


def test_el_pool_se_crea_una_sola_vez_y_se_abre():
    db.obtener_conexion_postgres()
    db.obtener_conexion_postgres()
    db.obtener_conexion_postgres()
    assert len(PoolFalso.creados) == 1
    assert PoolFalso.creados[0].abierto is True
    assert PoolFalso.creados[0].conninfo == "postgresql://usuario:clave@servidor/base"


def test_configuracion_del_pool():
    db.obtener_conexion_postgres()
    k = PoolFalso.creados[0].kwargs
    assert k["min_size"] == 1 and k["max_size"] == 10
    assert k["timeout"] == 20 and k["max_idle"] == 300 and k["max_lifetime"] == 1800
    assert k["kwargs"] == {"connect_timeout": 10}
    assert k["open"] is False                       # se abre explicitamente, una sola vez
    assert k["check"] is PoolFalso.check_connection  # prueba cada conexion antes de entregarla


def test_cerrar_devuelve_la_conexion_al_pool_y_no_la_cierra():
    conn = db.obtener_conexion_postgres()
    pool = PoolFalso.creados[0]
    conn.close()
    assert pool.devueltas == [pool.prestada]


def test_cerrar_dos_veces_devuelve_una_sola_vez():
    conn = db.obtener_conexion_postgres()
    conn.close()
    conn.close()
    assert len(PoolFalso.creados[0].devueltas) == 1


def test_cursor_commit_y_rollback_se_delegan_a_la_conexion_real():
    conn = db.obtener_conexion_postgres()
    assert conn.cursor() == "un-cursor"
    conn.cursor(row_factory="x")
    conn.commit()
    conn.rollback()
    assert PoolFalso.creados[0].prestada.eventos == [
        ("cursor", (), {}), ("cursor", (), {"row_factory": "x"}), "commit", "rollback"]


def test_cada_pedido_recibe_su_propio_envoltorio():
    a = db.obtener_conexion_postgres()
    b = db.obtener_conexion_postgres()
    a.close()
    assert b._conexion is not None and a._conexion is None


def test_una_lectura_deja_la_transaccion_abierta_y_se_deshace_al_devolver():
    conn = db.obtener_conexion_postgres()
    pool = PoolFalso.creados[0]
    pool.prestada.info.transaction_status = TransactionStatus.INTRANS
    conn.close()
    assert pool.prestada.eventos == ["rollback"] and pool.devueltas == [pool.prestada]


def test_una_conexion_limpia_se_devuelve_sin_rollback_extra():
    conn = db.obtener_conexion_postgres()
    pool = PoolFalso.creados[0]
    conn.commit()
    conn.close()
    assert pool.prestada.eventos == ["commit"]


def test_si_el_rollback_falla_igual_se_devuelve_al_pool():
    conn = db.obtener_conexion_postgres()
    pool = PoolFalso.creados[0]
    pool.prestada.info.transaction_status = TransactionStatus.INERROR

    def roto():
        raise RuntimeError("conexion rota")
    pool.prestada.rollback = roto
    conn.close()
    assert pool.devueltas == [pool.prestada]
