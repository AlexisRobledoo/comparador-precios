# 🛒 Comparador de Precios Rosario

App web full-stack que compara precios de supermercados de **Gran Rosario** con datos oficiales de **Precios Claros (SEPA)**. Buscás un producto, ves en qué cadena está más barato, y armás tu changuito para saber dónde te conviene hacer toda la compra.

🔗 **Probala online:** _(link de Render, se completa al publicar)_

![Python](https://img.shields.io/badge/Python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688)
![SQLite](https://img.shields.io/badge/SQLite-base%20de%20datos-003B57)
![License](https://img.shields.io/badge/license-MIT-green)

## ✨ Qué hace

- 🔍 **Buscador** de más de 34.000 productos, sin importar tildes ni el orden de las palabras.
- 🏷️ **Precio en cada sucursal**, del más barato al más caro, con las promociones vigentes.
- 🛒 **Changuito**: armás tu lista y te dice qué cadena te sale más barata en total, y cuánto ahorrás.
- 📖 **API pública documentada** en `/docs`.

Cadenas incluidas: Carrefour, Coto, Día, Jumbo, La Anónima y Vea (14 sucursales).

## 🏗️ Arquitectura

```
ZIP oficial SEPA (300 MB, todo el país)
        │
        ▼  etl.py  → filtra Gran Rosario por coordenadas, limpia y normaliza
        │
   precios.db  (SQLite: cadenas, sucursales, productos, precios)
        │
        ▼  api/main.py  → FastAPI: endpoints REST que consultan la base con SQL
        │
   web/  → HTML + CSS + JavaScript que consume la API
```

## 🔌 Endpoints de la API

| Método | Ruta | Qué devuelve |
|---|---|---|
| GET | `/api/resumen` | Fecha de los datos, cadenas y cantidades |
| GET | `/api/buscar?q=yerba` | Productos que coinciden, con precio mínimo y máximo |
| GET | `/api/productos/{ean}` | Precio del producto en cada sucursal |
| GET | `/api/sucursales` | Todas las sucursales con su ubicación |
| POST | `/api/changuito` | Total de una lista de productos en cada cadena |

La documentación interactiva (para probar cada endpoint desde el navegador) está en **`/docs`**.

## 🗄️ Base de datos

| Tabla | Contenido |
|---|---|
| `cadenas` | Supermercados (Coto, Carrefour…) |
| `sucursales` | Cada local, con dirección y coordenadas |
| `productos` | Cada producto identificado por su código de barras (EAN) |
| `precios` | Precio de cada producto en cada sucursal, con su promoción |

El **código de barras (EAN)** es lo que permite comparar: el mismo producto tiene el mismo código en todos los supermercados.

## 🚀 Cómo correrlo en tu compu

```bash
pip install -r requirements.txt
python -m uvicorn api.main:app --reload
```

Abrí `http://localhost:8000` para la web y `http://localhost:8000/docs` para la API.

## 🔄 Actualizar los precios

1. Descargá el ZIP del día desde [datos.produccion.gob.ar](https://datos.produccion.gob.ar/dataset/sepa-precios) y guardalo en `data/`.
2. Ejecutá `python etl.py data/<archivo>.zip`. Se regenera `precios.db`.
3. Subí el cambio a GitHub y la app online se actualiza sola.

## 🛠️ Tecnologías

Python · FastAPI · Pydantic · SQLite · SQL · HTML · CSS · JavaScript · Render

## ⚠️ Aclaración

Los precios son los que informan los propios supermercados al sistema oficial. Pueden no coincidir exactamente con el precio en góndola.

## 👤 Autor

**Alexis Robledo**, estudiante de la Tecnicatura en Programación (UGR, Rosario).
[Portfolio](https://alexisrobledoo.github.io) · [LinkedIn](https://linkedin.com/in/alexis-daniel-robledo) · [GitHub](https://github.com/AlexisRobledoo)
