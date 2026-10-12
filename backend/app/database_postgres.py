import os
import threading

from dotenv import load_dotenv
from psycopg.pq import TransactionStatus
from psycopg_pool import ConnectionPool


load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "Falta configurar la variable de entorno: DATABASE_URL"
    )


# Pool de conexiones. Abrir una conexion nueva a PostgreSQL en cada pedido (TCP + TLS +
# autenticacion) costaba cerca de medio segundo con la base en otro servidor; con el pool se
# reutilizan conexiones ya abiertas.
TAMANO_MINIMO_POOL = 1
TAMANO_MAXIMO_POOL = 10
SEGUNDOS_MAXIMOS_DE_ESPERA = 20      # esperando una conexion libre del pool
SEGUNDOS_INACTIVA_MAXIMA = 300       # conexiones de mas (sobre el minimo) que no se usan se cierran
SEGUNDOS_VIDA_MAXIMA = 1800          # toda conexion se renueva cada 30 minutos
SEGUNDOS_PARA_CONECTAR = 10

_pool = None
_candado_pool = threading.Lock()


def _obtener_pool():
    global _pool
    if _pool is None:
        with _candado_pool:
            if _pool is None:
                pool = ConnectionPool(
                    DATABASE_URL,
                    min_size=TAMANO_MINIMO_POOL,
                    max_size=TAMANO_MAXIMO_POOL,
                    timeout=SEGUNDOS_MAXIMOS_DE_ESPERA,
                    max_idle=SEGUNDOS_INACTIVA_MAXIMA,
                    max_lifetime=SEGUNDOS_VIDA_MAXIMA,
                    # prueba cada conexion antes de entregarla: si la base la cerro por inactividad,
                    # se descarta y se entrega otra en vez de fallar el pedido
                    check=ConnectionPool.check_connection,
                    kwargs={"connect_timeout": SEGUNDOS_PARA_CONECTAR},
                    open=False,
                )
                pool.open()
                _pool = pool
    return _pool


class ConexionDelPool:
    """Conexion prestada por el pool, con la misma forma de uso de antes.

    Los routers hacen `conn = obtener_conexion_postgres()` ... `conn.close()`. Aqui `close()` no
    cierra la conexion: la devuelve al pool, que la deja lista para el pedido siguiente (si quedo
    una transaccion abierta, el pool la deshace antes de reutilizarla).
    """

    def __init__(self, pool, conexion):
        self._pool = pool
        self._conexion = conexion

    def cursor(self, *args, **kwargs):
        return self._conexion.cursor(*args, **kwargs)

    def commit(self):
        self._conexion.commit()

    def rollback(self):
        self._conexion.rollback()

    def close(self):
        conexion, self._conexion = self._conexion, None
        if conexion is None:  # cerrar dos veces no devuelve dos veces
            return
        # Una lectura deja abierta la transaccion (psycopg la abre con la primera consulta). Se
        # deshace aqui, igual que haria el pool pero sin la advertencia que registra cada vez.
        if conexion.info.transaction_status != TransactionStatus.IDLE:
            try:
                conexion.rollback()
            except Exception:
                pass  # conexion rota: el pool la detecta al recibirla y la reemplaza
        self._pool.putconn(conexion)


def obtener_conexion_postgres():
    pool = _obtener_pool()
    return ConexionDelPool(pool, pool.getconn())
