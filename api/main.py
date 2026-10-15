"""
API del Comparador de Precios de Rosario — hecha con FastAPI.

Para correrla en tu compu:
    uvicorn api.main:app --reload

Después abrí:
    http://localhost:8000          → la web
    http://localhost:8000/docs     → documentación interactiva de la API
"""

import sqlite3
import unicodedata
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

RAIZ = Path(__file__).resolve().parent.parent
DB = RAIZ / "precios.db"

app = FastAPI(
    title="Comparador de Precios Rosario",
    description="API con precios de supermercados de Gran Rosario (datos oficiales de Precios Claros - SEPA).",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Conexión a la base de datos
# ---------------------------------------------------------------------------
def normalizar(texto):
    """'Leche CLÁSICA' → 'leche clasica'. Así buscar 'clasica' encuentra 'CLÁSICA'."""
    if texto is None:
        return ""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.lower()


def conectar():
    # Abrimos en modo solo lectura: la API nunca modifica los datos
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row          # filas como diccionarios: fila["precio"]
    con.create_function("normalizar", 1, normalizar, deterministic=True)
    return con


con = conectar()


def consultar(sql, parametros=()):
    return [dict(fila) for fila in con.execute(sql, parametros).fetchall()]


# Precio final = el de la promo si hay, si no el de lista
PRECIO_FINAL = "COALESCE(pr.precio_promo, pr.precio)"


# ---------------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------------
@app.get("/api/resumen", tags=["General"])
def resumen():
    """Datos generales: fecha de los precios, cadenas y cantidades."""
    fecha = consultar("SELECT valor FROM info WHERE clave = 'fecha_datos'")
    return {
        "fecha_datos": fecha[0]["valor"] if fecha else None,
        "cadenas": consultar("SELECT id, nombre FROM cadenas ORDER BY nombre"),
        "sucursales": consultar("SELECT COUNT(*) AS n FROM sucursales")[0]["n"],
        "productos": consultar("SELECT COUNT(*) AS n FROM productos")[0]["n"],
        "precios": consultar("SELECT COUNT(*) AS n FROM precios")[0]["n"],
    }


@app.get("/api/sucursales", tags=["General"])
def sucursales():
    """Todas las sucursales con su ubicación."""
    return consultar("""
        SELECT s.id, c.nombre AS cadena, s.nombre, s.direccion, s.localidad, s.latitud, s.longitud
        FROM sucursales s JOIN cadenas c ON c.id = s.cadena_id
        ORDER BY c.nombre, s.nombre
    """)


@app.get("/api/buscar", tags=["Productos"])
def buscar(q: str = Query(..., min_length=2, description="Texto a buscar, por ejemplo: leche serenisima"),
           limite: int = Query(30, ge=1, le=100)):
    """Busca productos por nombre o marca. Cada palabra tiene que aparecer (en cualquier orden).
    Primero muestra los que están en más cadenas (los más fáciles de comparar)."""
    palabras = [p for p in normalizar(q).split() if p]
    condiciones = " AND ".join(["normalizar(p.descripcion || ' ' || COALESCE(p.marca, '')) LIKE ?"] * len(palabras))
    parametros = [f"%{p}%" for p in palabras]

    return consultar(f"""
        SELECT p.ean, p.descripcion, p.marca, p.presentacion,
               COUNT(DISTINCT s.cadena_id) AS cadenas,
               MIN({PRECIO_FINAL})         AS precio_min,
               MAX({PRECIO_FINAL})         AS precio_max
        FROM productos p
        JOIN precios pr   ON pr.ean = p.ean
        JOIN sucursales s ON s.id = pr.sucursal_id
        WHERE {condiciones}
        GROUP BY p.ean
        -- Primero los que EMPIEZAN con la primera palabra (si buscás "leche",
        -- la leche aparece antes que el "dulce de leche"), después los que están en más cadenas
        ORDER BY normalizar(p.descripcion) LIKE ? DESC, cadenas DESC, p.descripcion
        LIMIT ?
    """, parametros + [f"{palabras[0]}%", limite])


@app.get("/api/productos/{ean}", tags=["Productos"])
def producto(ean: str):
    """Detalle de un producto y su precio en cada sucursal, del más barato al más caro."""
    datos = consultar("SELECT * FROM productos WHERE ean = ?", (ean,))
    if not datos:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    precios = consultar(f"""
        SELECT c.nombre AS cadena, s.nombre AS sucursal, s.direccion, s.localidad,
               pr.precio, pr.precio_promo, pr.promo, {PRECIO_FINAL} AS precio_final
        FROM precios pr
        JOIN sucursales s ON s.id = pr.sucursal_id
        JOIN cadenas c    ON c.id = s.cadena_id
        WHERE pr.ean = ?
        ORDER BY precio_final, c.nombre
    """, (ean,))

    finales = [p["precio_final"] for p in precios]
    ahorro = (max(finales) - min(finales)) if finales else 0
    return {**datos[0], "precios": precios, "ahorro_maximo": ahorro}


class Item(BaseModel):
    ean: str
    cantidad: int = Field(1, ge=1, le=99)


class Changuito(BaseModel):
    items: list[Item] = Field(..., min_length=1, max_length=100)


@app.post("/api/changuito", tags=["Changuito"])
def changuito(carrito: Changuito):
    """Recibe una lista de productos y calcula cuánto sale en cada cadena.
    Para cada cadena usa la sucursal más barata de ese producto."""
    eans = [i.ean for i in carrito.items]
    cantidades = {i.ean: i.cantidad for i in carrito.items}
    marcas = ",".join("?" * len(eans))

    filas = consultar(f"""
        SELECT c.nombre AS cadena, pr.ean, MIN({PRECIO_FINAL}) AS precio
        FROM precios pr
        JOIN sucursales s ON s.id = pr.sucursal_id
        JOIN cadenas c    ON c.id = s.cadena_id
        WHERE pr.ean IN ({marcas})
        GROUP BY c.nombre, pr.ean
    """, eans)

    por_cadena = {}
    for f in filas:
        info = por_cadena.setdefault(f["cadena"], {"cadena": f["cadena"], "total": 0, "encontrados": 0})
        info["total"] += f["precio"] * cantidades[f["ean"]]
        info["encontrados"] += 1

    resultado = []
    for info in por_cadena.values():
        info["faltantes"] = len(eans) - info["encontrados"]
        info["total"] = round(info["total"], 2)
        resultado.append(info)

    # Primero las cadenas que tienen TODO; dentro de eso, la más barata
    resultado.sort(key=lambda r: (r["faltantes"], r["total"]))
    return {"productos": len(eans), "cadenas": resultado}


# ---------------------------------------------------------------------------
# La web (carpeta web/) se sirve desde la misma app, en la raíz "/"
# Va al final para que no tape las rutas /api/...
# ---------------------------------------------------------------------------
app.mount("/", StaticFiles(directory=RAIZ / "web", html=True), name="web")
