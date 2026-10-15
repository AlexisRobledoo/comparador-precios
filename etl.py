"""
ETL: Extract, Transform, Load.

Lee el ZIP oficial de Precios Claros (SEPA), se queda solo con las sucursales
de Gran Rosario y guarda todo en una base de datos SQLite (precios.db).

Uso:
    python etl.py data/sepa_viernes.zip
"""

import csv
import io
import sqlite3
import sys
import zipfile
from pathlib import Path

DB = Path("precios.db")

# Rectángulo que cubre Gran Rosario (Rosario, Funes, Fisherton, Granadero Baigorria...)
# Filtramos por coordenadas porque la columna "localidad" viene cargada de mil formas
# distintas: "Rosario", "ROSARIO", "Fisherton", y hasta "SANTA FE".
LAT_MIN, LAT_MAX = -33.08, -32.85
LON_MIN, LON_MAX = -60.90, -60.58

# Nombres más cortos y prolijos para mostrar
NOMBRES_CADENA = {
    "COTO CICSA": "Coto",
    "Hipermercado Carrefour": "Carrefour",
    "Supermercados DIA": "Día",
    "La Anonima": "La Anónima",
}

# Cadenas que no son supermercados (por ejemplo, tiendas de estaciones de servicio)
EXCLUIR = {"Axion Energy", "ESTACION LIMA S.A."}

ESQUEMA = """
DROP TABLE IF EXISTS info;
DROP TABLE IF EXISTS precios;
DROP TABLE IF EXISTS productos;
DROP TABLE IF EXISTS sucursales;
DROP TABLE IF EXISTS cadenas;

CREATE TABLE cadenas (
    id      TEXT PRIMARY KEY,      -- "comercio-bandera", por ejemplo "10-2"
    nombre  TEXT NOT NULL
);

CREATE TABLE sucursales (
    id         TEXT PRIMARY KEY,   -- "comercio-bandera-sucursal"
    cadena_id  TEXT NOT NULL REFERENCES cadenas(id),
    nombre     TEXT,
    direccion  TEXT,
    localidad  TEXT,
    latitud    REAL,
    longitud   REAL
);

CREATE TABLE productos (
    ean          TEXT PRIMARY KEY, -- código de barras: es igual en todos los supermercados
    descripcion  TEXT NOT NULL,
    marca        TEXT,
    presentacion TEXT
);

CREATE TABLE info (
    clave  TEXT PRIMARY KEY,       -- datos generales, por ejemplo la fecha de los precios
    valor  TEXT
);

CREATE TABLE precios (
    sucursal_id   TEXT NOT NULL REFERENCES sucursales(id),
    ean           TEXT NOT NULL REFERENCES productos(ean),
    precio        REAL NOT NULL,   -- precio de lista
    precio_promo  REAL,            -- precio con promoción (si hay)
    promo         TEXT,            -- texto de la promoción
    PRIMARY KEY (sucursal_id, ean)
);
"""

INDICES = """
CREATE INDEX idx_precios_ean ON precios(ean);
CREATE INDEX idx_productos_desc ON productos(descripcion);
"""


def a_numero(texto):
    """Convierte '1234.5' a 1234.5. Si viene vacío o raro, devuelve None."""
    try:
        valor = float(texto.replace(",", "."))
        return valor if valor > 0 else None
    except (ValueError, AttributeError):
        return None


def leer_csv(zip_interno, nombre):
    """Lee un CSV con separador | y devuelve filas como diccionarios.
    Los archivos terminan con una línea 'Ultima actualizacion: ...' que salteamos."""
    with zip_interno.open(nombre) as f:
        # utf-8-sig: algunas empresas guardan el archivo con un carácter invisible (BOM) al inicio
        texto = io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace")
        lineas = (linea.replace("\0", "") for linea in texto)  # algunos archivos traen bytes nulos
        lector = csv.DictReader(lineas, delimiter="|")
        lector.fieldnames = [c.strip().lower() for c in lector.fieldnames]  # encabezados prolijos
        for fila in lector:
            if (fila.get("id_comercio") or "").startswith("Ultima"):
                continue
            yield {k: (v or "") for k, v in fila.items() if k}


def procesar(ruta_zip):
    con = sqlite3.connect(DB)
    con.executescript(ESQUEMA)

    total_precios = 0
    fecha_datos = ""
    externo = zipfile.ZipFile(ruta_zip)

    # El ZIP del gobierno tiene adentro un ZIP por cada empresa
    for nombre in externo.namelist():
        if not nombre.endswith(".zip"):
            continue
        try:
            interno = zipfile.ZipFile(io.BytesIO(externo.read(nombre)))
        except zipfile.BadZipFile:
            print(f"⚠️  Archivo dañado, lo salteo: {nombre}")
            continue

        # --- 1) Cadenas (banderas) de esta empresa ---
        cadenas = {}
        for c in leer_csv(interno, "comercio.csv"):
            if c["comercio_bandera_nombre"].strip() in EXCLUIR:
                continue
            cid = f"{c['id_comercio']}-{c['id_bandera']}"
            nombre_cadena = c["comercio_bandera_nombre"].strip()
            cadenas[cid] = NOMBRES_CADENA.get(nombre_cadena, nombre_cadena)
            fecha_datos = max(fecha_datos, c.get("comercio_ultima_actualizacion", "")[:10])

        # --- 2) Sucursales que están en Gran Rosario ---
        sucursales = {}
        for s in leer_csv(interno, "sucursales.csv"):
            cid = f"{s['id_comercio']}-{s['id_bandera']}"
            try:
                lat, lon = float(s["sucursales_latitud"]), float(s["sucursales_longitud"])
            except (TypeError, ValueError):
                continue
            if cid not in cadenas or not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
                continue
            sid = f"{cid}-{s['id_sucursal']}"
            direccion = f"{s['sucursales_calle'].strip()} {s['sucursales_numero'].strip()}".strip()
            localidad = s["sucursales_localidad"].strip().title()
            if localidad in ("Santa Fe", "Capital", ""):  # algunas cadenas cargan la provincia acá
                localidad = "Gran Rosario"
            sucursales[sid] = (sid, cid, s["sucursales_nombre"].strip(), direccion,
                               localidad, lat, lon)

        if not sucursales:
            continue

        usadas = {s[1] for s in sucursales.values()}
        con.executemany("INSERT OR IGNORE INTO cadenas VALUES (?, ?)",
                        [(cid, n) for cid, n in cadenas.items() if cid in usadas])
        con.executemany("INSERT OR REPLACE INTO sucursales VALUES (?, ?, ?, ?, ?, ?, ?)",
                        sucursales.values())

        # --- 3) Precios: solo de esas sucursales y con código de barras válido ---
        productos, precios = {}, []
        for p in leer_csv(interno, "productos.csv"):
            sid = f"{p['id_comercio']}-{p['id_bandera']}-{p['id_sucursal']}"
            if sid not in sucursales or p["productos_ean"] != "1":
                continue
            ean = p["id_producto"].strip().lstrip("0")
            precio = a_numero(p["productos_precio_lista"])
            if not ean or not precio:
                continue

            promo = a_numero(p["productos_precio_unitario_promo1"] or "")
            # Solo aceptamos promos razonables (más baratas y no más del 70% de descuento)
            if promo and not (precio * 0.3 <= promo < precio):
                promo = None

            cantidad = p["productos_cantidad_presentacion"].strip()
            unidad = p["productos_unidad_medida_presentacion"].strip()
            productos.setdefault(ean, (ean, " ".join(p["productos_descripcion"].split()),
                                       p["productos_marca"].strip(), f"{cantidad} {unidad}".strip()))
            precios.append((sid, ean, precio, promo,
                            (p["productos_leyenda_promo1"] or "").strip() if promo else None))

        con.executemany("INSERT OR IGNORE INTO productos VALUES (?, ?, ?, ?)", productos.values())
        con.executemany("INSERT OR REPLACE INTO precios VALUES (?, ?, ?, ?, ?)", precios)
        con.commit()
        total_precios += len(precios)
        nombres = ", ".join(sorted({cadenas[s[1]] for s in sucursales.values()}))
        print(f"✅ {nombres}: {len(sucursales)} sucursales, {len(precios):,} precios")

    con.execute("INSERT INTO info VALUES ('fecha_datos', ?)", (fecha_datos,))
    con.commit()
    con.executescript(INDICES)
    con.execute("VACUUM")  # compacta el archivo
    con.close()
    print(f"\nListo: {total_precios:,} precios guardados en {DB} ({DB.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python etl.py data/<archivo_sepa>.zip")
        sys.exit(1)
    procesar(sys.argv[1])
