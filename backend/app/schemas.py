import re
from decimal import Decimal
from typing import Annotated, List, Literal, Optional

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

# 4a. Descripcion comercial de un articulo (panel administrativo).
# Un texto vacio (o solo espacios) se guarda como NULL: "sin descripcion".
class DescripcionEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    descripcion: Optional[str] = Field(..., max_length=2000)

    @field_validator("descripcion")
    @classmethod
    def vacio_es_nulo(cls, valor):
        return valor or None

# 4b. Cambio parcial de un banner (panel administrativo)
class BannerActualizar(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    alt: Optional[str] = Field(default=None, min_length=1, max_length=500)
    orden: Optional[int] = Field(default=None, ge=0, le=2147483647)  # integer de PostgreSQL
    activo: Optional[bool] = None

    @model_validator(mode="after")
    def al_menos_un_campo(self):
        if not self.model_fields_set:
            raise ValueError("Indique al menos un campo: alt, orden o activo")
        if any(getattr(self, c) is None for c in self.model_fields_set):
            raise ValueError("Los campos enviados no pueden ser null")
        return self

# 4c. Nuevo orden completo de los banners (panel administrativo)
class BannersReordenar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: List[Annotated[int, Field(gt=0, le=2147483647)]] = Field(min_length=1, max_length=500)

    @field_validator("ids")
    @classmethod
    def sin_ids_repetidos(cls, valor):
        if len(set(valor)) != len(valor):
            raise ValueError("La lista de ids tiene elementos repetidos")
        return valor

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


class LoginEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usuario: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=200)

    @field_validator("usuario")
    @classmethod
    def usuario_normalizado(cls, valor):
        return valor.strip().lower()


class UsuarioNuevo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usuario: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=1, max_length=200)
    es_admin: bool = False

    @field_validator("usuario")
    @classmethod
    def usuario_valido(cls, valor):
        valor = valor.strip().lower()
        if not re.fullmatch(r"[a-z0-9._-]{3,50}", valor):
            raise ValueError("El usuario solo admite letras, numeros, punto, guion y guion bajo")
        return valor


class UsuarioCambio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activo: Optional[bool] = None
    es_admin: Optional[bool] = None

    @model_validator(mode="after")
    def algo_que_cambiar(self):
        if self.activo is None and self.es_admin is None:
            raise ValueError("Indique activo y/o es_admin")
        return self


class PasswordNueva(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(..., min_length=1, max_length=200)


class CambioDePassword(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actual: str = Field(..., min_length=1, max_length=200)
    nueva: str = Field(..., min_length=1, max_length=200)
