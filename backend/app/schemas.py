from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# 1. Definimos cómo luce un artículo individual dentro del carrito
# Coincide con lo que JavaScript tiene en memoria
class ItemCarrito(BaseModel):
    id: int = Field(gt=0)
    nombre: str
    precio: float
    cantidad: Decimal = Field(
        ge=Decimal("0.001"),
        max_digits=9,
        decimal_places=3
    )

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
    art_kit: bool
    tipo_kit: Optional[Literal["PRESENTACION", "COMBO"]] = None
    uni_cod_com: Optional[int] = None
    uni_cod_ven: Optional[int] = None
    version_actual: int = Field(gt=0)

    @model_validator(mode="after")
    def tipo_kit_consistente_con_art_kit(self):
        if not self.art_kit and self.tipo_kit is not None:
            raise ValueError(
                f"art_kit es False pero tipo_kit='{self.tipo_kit}' "
                "(tipo_kit debe ser NULL cuando art_kit=False)"
            )
        return self

# 4. Cambio de visibilidad web de un articulo (panel administrativo)
class MostrarWebEntrada(BaseModel):
    mostrar_web: bool

# 5. Composicion de un kit (SQL Server -> PostgreSQL)
class ComponenteKit(BaseModel):
    idkit: int = Field(gt=0)
    art_cod: int = Field(gt=0, lt=10**18)
    art_cantidad: Decimal = Field(gt=0, max_digits=9, decimal_places=3)

class ArticulosKitSync(BaseModel):
    art_codkit: int = Field(gt=0, lt=10**18)
    componentes: List[ComponenteKit]
    version_actual: int = Field(gt=0)

    @field_validator("componentes")
    @classmethod
    def sin_componentes_duplicados(cls, valor):
        vistos = set()
        for c in valor:
            if c.art_cod in vistos:
                raise ValueError(f"art_cod {c.art_cod} esta repetido en componentes")
            vistos.add(c.art_cod)
        return valor

# 6. Stock de un articulo (SQL Server -> PostgreSQL)
class StockSync(BaseModel):
    art_cod: int = Field(gt=0, lt=10**18)
    cantidad: Decimal = Field(ge=0, max_digits=9, decimal_places=3)
    version_actual: int = Field(gt=0)
