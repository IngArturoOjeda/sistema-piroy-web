from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# 1. Definimos cómo luce un artículo individual dentro del carrito
# Coincide con lo que JavaScript tiene en memoria
class ItemCarrito(BaseModel):
    id: int = Field(gt=0)
    nombre: str
    precio: float
    cantidad: int = Field(gt=0, le=100)

# 2. Definimos cómo luce el pedido completo que enviará el cliente
# Incluye los datos únicos de entrega y la lista de sus productos
class PedidoEntrada(BaseModel):
    cliente_nombre: str
    cliente_direccion: str
    cliente_telefono: str 
    productos: List[ItemCarrito] # Una lista que contiene objetos del tipo ItemCarrito

# 3. Artículo enviado por el sincronizador local (SQL Server -> PostgreSQL)
class ArticuloSync(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    art_cod: int = Field(gt=0, lt=10**18)
    art_nombre: str = Field(min_length=1)
    art_preciobase: Decimal = Field(
        ge=0,
        max_digits=14,
        decimal_places=0
    )
    tipoart_cod: int
    art_foto: Optional[str] = None
    art_estado: str = Field(pattern="^[SN]$")
    llevar_web: bool
    version_actual: int = Field(gt=0)
