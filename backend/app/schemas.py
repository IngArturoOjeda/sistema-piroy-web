from pydantic import BaseModel
from typing import List

# 1. Definimos cómo luce un artículo individual dentro del carrito
# Coincide con lo que JavaScript tiene en memoria
class ItemCarrito(BaseModel):
    id: int
    nombre: str
    precio: float
    cantidad: int

# 2. Definimos cómo luce el pedido completo que enviará el cliente
# Incluye los datos únicos de entrega y la lista de sus productos
class PedidoEntrada(BaseModel):
    cliente_nombre: str
    cliente_direccion: str
    cliente_telefono: str
    productos: List[ItemCarrito] # Una lista que contiene objetos del tipo ItemCarrito
