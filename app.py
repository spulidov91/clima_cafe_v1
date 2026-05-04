import json
import os
import unicodedata
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from train_model import FEATS_SELECT_TOTAL, TARGET, carga_info


APP_NAME = "API Clima Café"

DATA_FILE = Path(os.getenv("DATA_FILE", "Data anual/data_anual_total.xlsx"))
MODEL_FILE = Path(os.getenv("MODEL_FILE", "modelos/modelo_clima_cafe.joblib"))

TRM_COP_USD = float(os.getenv("TRM_COP_USD", "3650"))
PRECIO_INTERNACIONAL_USD_LB = float(os.getenv("PRECIO_INTERNACIONAL_USD_LB", "3.30"))
PRECIO_LOCAL_COP_KG = float(os.getenv("PRECIO_LOCAL_COP_KG", "12500"))
PORCENTAJE_COBERTURA = float(os.getenv("PORCENTAJE_COBERTURA", "0.15"))

app = FastAPI(
    title=APP_NAME,
    version="1.0.0",
    description="API para estimar cosecha de café y valor de cobertura a partir de datos climáticos/satelitales.",
)

_raw_df_cache: Optional[pd.DataFrame] = None
_processed_df_cache: Optional[pd.DataFrame] = None
_artifact_cache = None


class ConsultaRequest(BaseModel):
    numero_identidad: str = Field(..., examples=["1019000363"])
    municipio: str = Field(..., examples=["Barbosa"])
    area_ha: float = Field(..., gt=0, examples=[2.5])
    departamento: Optional[str] = Field(
        default=None,
        description="Opcional. Útil si hay municipios con el mismo nombre en varios departamentos.",
        examples=["Santander"],
    )
    year: Optional[int] = Field(
        default=None,
        description="Opcional. Si no se envía, se usa el año más reciente disponible para el municipio.",
        examples=[2024],
    )


class ConsultaResponse(BaseModel):
    tipo_respuesta_api: int
    numero_identidad: str
    municipio: str
    departamento: Optional[str]
    year_usado: int
    area_ha: float
    rendimiento_estimado_ton_ha: float
    cosecha_estimada_ton: float
    trm_cop_usd: float
    precio_internacional_usd_lb: float
    precio_local_cop_kg: float
    valor_estimado_cosecha_cop: float
    porcentaje_cobertura: float
    valor_cobertura_cop: float
    mensaje: str


def normalize_text(value: str) -> str:
    value = "" if value is None else str(value)
    value = value.strip().lower()
    value = "".join(
        c for c in unicodedata.normalize("NFD", value)
        if unicodedata.category(c) != "Mn"
    )
    return value


def load_raw_df() -> pd.DataFrame:
    global _raw_df_cache

    if _raw_df_cache is not None:
        return _raw_df_cache

    if not DATA_FILE.exists():
        raise FileNotFoundError(f"No existe DATA_FILE: {DATA_FILE}")

    df = pd.read_excel(DATA_FILE)
    df["_municipio_norm"] = df["Municipio"].apply(normalize_text)
    df["_departamento_norm"] = df["Departamento"].apply(normalize_text)
    _raw_df_cache = df
    return _raw_df_cache


def load_processed_df() -> pd.DataFrame:
    global _processed_df_cache

    if _processed_df_cache is not None:
        return _processed_df_cache

    raw_df = load_raw_df()
    processed = carga_info(raw_df.drop(columns=[c for c in raw_df.columns if c.startswith("_")], errors="ignore"))

    mpio_parts = processed["Mpio"].astype(str).str.split("_", n=1, expand=True)
    processed["_municipio_norm"] = mpio_parts[0].apply(normalize_text)
    processed["_departamento_norm"] = mpio_parts[1].apply(normalize_text) if mpio_parts.shape[1] > 1 else ""
    processed["_departamento"] = mpio_parts[1] if mpio_parts.shape[1] > 1 else None

    _processed_df_cache = processed
    return _processed_df_cache


def load_artifact():
    global _artifact_cache

    if _artifact_cache is not None:
        return _artifact_cache

    if not MODEL_FILE.exists():
        raise FileNotFoundError(f"No existe MODEL_FILE: {MODEL_FILE}")

    _artifact_cache = joblib.load(MODEL_FILE)
    return _artifact_cache


def get_model_row(municipio: str, departamento: Optional[str], year: Optional[int]) -> pd.Series:
    df = load_processed_df()

    municipio_norm = normalize_text(municipio)
    filtered = df[df["_municipio_norm"] == municipio_norm].copy()

    if departamento:
        departamento_norm = normalize_text(departamento)
        filtered = filtered[filtered["_departamento_norm"] == departamento_norm].copy()

    if filtered.empty:
        raise HTTPException(
            status_code=404,
            detail=(
                "No se encontró información para el municipio/departamento solicitado. "
                "Consulta GET /municipios para ver opciones disponibles."
            ),
        )

    if year is not None:
        filtered = filtered[filtered["Year"] == year].copy()
        if filtered.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No hay información para el año solicitado: {year}",
            )

    filtered = filtered.sort_values("Year", ascending=False)
    return filtered.iloc[0]


@app.on_event("startup")
def startup_event():
    load_raw_df()
    load_processed_df()
    load_artifact()


@app.get("/health")
def health():
    raw_df = load_raw_df()
    processed_df = load_processed_df()
    artifact = load_artifact()

    return {
        "status": "ok",
        "app": APP_NAME,
        "data_file": str(DATA_FILE),
        "model_file": str(MODEL_FILE),
        "rows_raw": len(raw_df),
        "rows_processed": len(processed_df),
        "features": artifact.get("features", FEATS_SELECT_TOTAL),
        "metrics": artifact.get("metrics", {}),
    }


@app.get("/municipios")
def municipios():
    df = load_processed_df()
    out = (
        df[["Mpio", "Year"]]
        .drop_duplicates()
        .sort_values(["Mpio", "Year"])
        .to_dict(orient="records")
    )
    return {"total": len(out), "municipios": out}


@app.post("/cache/refresh")
def cache_refresh():
    global _raw_df_cache, _processed_df_cache, _artifact_cache

    _raw_df_cache = None
    _processed_df_cache = None
    _artifact_cache = None

    return health()


@app.post("/consulta", response_model=ConsultaResponse)
def consulta(payload: ConsultaRequest):
    artifact = load_artifact()
    pipeline = artifact["pipeline"]

    row = get_model_row(payload.municipio, payload.departamento, payload.year)

    X = pd.DataFrame([row[FEATS_SELECT_TOTAL].to_dict()])
    rendimiento_estimado = float(pipeline.predict(X)[0])

    # Protección básica ante predicciones negativas.
    rendimiento_estimado = max(0.0, rendimiento_estimado)

    # Supuesto operativo: Rendimiento está en toneladas/hectárea.
    cosecha_estimada_ton = rendimiento_estimado * payload.area_ha

    valor_estimado_cosecha_cop = cosecha_estimada_ton * 1000 * PRECIO_LOCAL_COP_KG
    valor_cobertura_cop = valor_estimado_cosecha_cop * PORCENTAJE_COBERTURA

    departamento_usado = row.get("_departamento")
    year_usado = int(row["Year"])

    mensaje = (
        f"Según la información climática y satelital disponible para {payload.municipio}"
        f"{' - ' + str(departamento_usado) if departamento_usado else ''}, "
        f"usando el año {year_usado}, la cosecha estimada para {payload.area_ha:.2f} hectáreas "
        f"es de {cosecha_estimada_ton:.2f} toneladas. "
        f"El valor estimado de la cosecha es {valor_estimado_cosecha_cop:,.0f} COP "
        f"y el valor de cobertura estimado es {valor_cobertura_cop:,.0f} COP."
    )

    return ConsultaResponse(
        tipo_respuesta_api=200,
        numero_identidad=payload.numero_identidad,
        municipio=payload.municipio,
        departamento=str(departamento_usado) if departamento_usado is not None else payload.departamento,
        year_usado=year_usado,
        area_ha=round(payload.area_ha, 4),
        rendimiento_estimado_ton_ha=round(rendimiento_estimado, 6),
        cosecha_estimada_ton=round(cosecha_estimada_ton, 4),
        trm_cop_usd=TRM_COP_USD,
        precio_internacional_usd_lb=PRECIO_INTERNACIONAL_USD_LB,
        precio_local_cop_kg=PRECIO_LOCAL_COP_KG,
        valor_estimado_cosecha_cop=round(valor_estimado_cosecha_cop, 2),
        porcentaje_cobertura=PORCENTAJE_COBERTURA,
        valor_cobertura_cop=round(valor_cobertura_cop, 2),
        mensaje=mensaje,
    )

# -------------------------------
# Frontend estático de la solución
# -------------------------------
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/", include_in_schema=False)
def frontend_home():
    return FileResponse("frontend/index.html")
