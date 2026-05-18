import json
import os
import unicodedata
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from train_model import FEATS_SELECT_TOTAL, TARGET, carga_info


APP_NAME = "API Clima Café"

BASE_DIR = Path(__file__).resolve().parent


def path_from_env(env_name: str, default: str) -> Path:
    value = Path(os.getenv(env_name, default))
    return value if value.is_absolute() else BASE_DIR / value


DATA_FILE = path_from_env("DATA_FILE", "Data anual/data_anual_total.xlsx")
PRED_FILE = path_from_env("PRED_FILE", "Data anual/total_pred_final.xlsx")
MODEL_FILE = path_from_env("MODEL_FILE", "modelos/modelo_clima_cafe.joblib")
FRONTEND_DIR = path_from_env("FRONTEND_DIR", "frontend")
GEOJSON_DIR = path_from_env("GEOJSON_DIR", "geojson")

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
_predictions_df_cache: Optional[pd.DataFrame] = None
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

    # Resultado principal
    rendimiento_estimado_ton_ha: float
    rendimiento_predicho: float
    cosecha_estimada_ton: float
    cosecha_estimada_kg: float

    # Intervalos de confianza para el frontend
    rendimiento_inf: Optional[float] = None
    rendimiento_sup: Optional[float] = None
    cosecha_estimada_inf_kg: Optional[float] = None
    cosecha_estimada_sup_kg: Optional[float] = None
    valor_estimado_cosecha_inf_cop: Optional[float] = None
    valor_estimado_cosecha_sup_cop: Optional[float] = None

    # Valores económicos
    trm_cop_usd: float
    precio_internacional_usd_lb: float
    precio_local_cop_kg: float
    valor_estimado_cosecha_cop: float
    porcentaje_cobertura: float
    valor_cobertura_cop: float
    valor_maximo_indemnizar_cop: Optional[float] = None

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
    processed["_mpio_norm"] = processed["Mpio"].apply(normalize_text)

    _processed_df_cache = processed
    return _processed_df_cache


def load_predictions_df() -> Optional[pd.DataFrame]:
    """
    Carga Data anual/total_pred_final.xlsx para calcular intervalos por municipio.
    El notebook 4 calcula el promedio de errores positivos y negativos por municipio.
    """
    global _predictions_df_cache

    if _predictions_df_cache is not None:
        return _predictions_df_cache

    if not PRED_FILE.exists():
        _predictions_df_cache = pd.DataFrame()
        return _predictions_df_cache

    pred = pd.read_excel(PRED_FILE)

    required = {"Mpio", "Year"}
    if not required.issubset(set(pred.columns)):
        _predictions_df_cache = pd.DataFrame()
        return _predictions_df_cache

    pred["_mpio_norm"] = pred["Mpio"].apply(normalize_text)
    _predictions_df_cache = pred
    return _predictions_df_cache


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


def get_error_interval_for_row(row: pd.Series, year_usado: int, artifact) -> tuple[float, float]:
    """
    Retorna errores promedio negativo y positivo para el municipio.
    Si no hay archivo de predicciones o no hay columna Error, usa RMSE del artefacto como respaldo.
    """
    pred = load_predictions_df()
    mpio_norm = normalize_text(row.get("Mpio", ""))

    if pred is not None and not pred.empty and "Error" in pred.columns:
        pred_mpio = pred[(pred["_mpio_norm"] == mpio_norm) & (pred["Year"] <= year_usado)].copy()

        if not pred_mpio.empty:
            error_pos = pred_mpio.loc[pred_mpio["Error"] > 0, "Error"].mean()
            error_neg = pred_mpio.loc[pred_mpio["Error"] < 0, "Error"].mean()

            if pd.notna(error_pos) and pd.notna(error_neg):
                return float(error_neg), float(error_pos)

    metrics = artifact.get("metrics", {}) if isinstance(artifact, dict) else {}
    rmse = (
        metrics.get("rmse_oot")
        or metrics.get("rmse_test")
        or metrics.get("rmse_train")
        or 0
    )
    rmse = float(rmse) if rmse is not None else 0.0
    return -rmse, rmse


def get_valor_maximo_indemnizar(row: pd.Series, year_usado: int, area_ha: float) -> Optional[float]:
    """
    Aproxima el valor máximo a indemnizar usando la lógica del notebook 4:
    umbral = promedio histórico municipal - desviación estándar municipal
    valor máximo = costo en umbral - costo en mínimo histórico
    """
    df = load_processed_df()
    mpio_norm = normalize_text(row.get("Mpio", ""))

    hist = df[(df["_mpio_norm"] == mpio_norm) & (df["Year"] != year_usado)].copy()
    if hist.empty or TARGET not in hist.columns:
        return None

    rendimiento_avg = hist[TARGET].astype(float).mean()
    rendimiento_std = hist[TARGET].astype(float).std()
    rendimiento_min = hist[TARGET].astype(float).min()

    if pd.isna(rendimiento_avg) or pd.isna(rendimiento_std) or pd.isna(rendimiento_min):
        return None

    rendimiento_umbral = max(0.0, float(rendimiento_avg - rendimiento_std))
    rendimiento_min = max(0.0, float(rendimiento_min))

    costo_umbral = rendimiento_umbral * area_ha * 1000 * PRECIO_LOCAL_COP_KG
    costo_minimo = rendimiento_min * area_ha * 1000 * PRECIO_LOCAL_COP_KG

    return max(0.0, costo_umbral - costo_minimo)


@app.on_event("startup")
def startup_event():
    load_raw_df()
    load_processed_df()
    load_predictions_df()
    load_artifact()


@app.get("/health")
def health():
    raw_df = load_raw_df()
    processed_df = load_processed_df()
    pred_df = load_predictions_df()
    artifact = load_artifact()

    return {
        "status": "ok",
        "app": APP_NAME,
        "data_file": str(DATA_FILE),
        "pred_file": str(PRED_FILE),
        "model_file": str(MODEL_FILE),
        "frontend_dir": str(FRONTEND_DIR),
        "geojson_dir": str(GEOJSON_DIR),
        "geojson_exists": GEOJSON_DIR.exists(),
        "rows_raw": len(raw_df),
        "rows_processed": len(processed_df),
        "rows_predictions": 0 if pred_df is None else len(pred_df),
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
    global _raw_df_cache, _processed_df_cache, _predictions_df_cache, _artifact_cache

    _raw_df_cache = None
    _processed_df_cache = None
    _predictions_df_cache = None
    _artifact_cache = None

    return health()


@app.post("/consulta", response_model=ConsultaResponse)
def consulta(payload: ConsultaRequest):
    artifact = load_artifact()
    pipeline = artifact["pipeline"]

    row = get_model_row(payload.municipio, payload.departamento, payload.year)
    year_usado = int(row["Year"])

    X = pd.DataFrame([row[FEATS_SELECT_TOTAL].to_dict()])
    rendimiento_estimado = float(pipeline.predict(X)[0])

    # Protección básica ante predicciones negativas.
    rendimiento_estimado = max(0.0, rendimiento_estimado)

    # Intervalos de confianza por error promedio municipal.
    error_neg, error_pos = get_error_interval_for_row(row, year_usado, artifact)
    rendimiento_inf = max(0.0, rendimiento_estimado + error_neg)
    rendimiento_sup = max(rendimiento_inf, rendimiento_estimado + error_pos)

    # Supuesto operativo: Rendimiento está en toneladas/hectárea.
    cosecha_estimada_ton = rendimiento_estimado * payload.area_ha
    cosecha_estimada_kg = cosecha_estimada_ton * 1000

    cosecha_estimada_inf_kg = rendimiento_inf * payload.area_ha * 1000
    cosecha_estimada_sup_kg = rendimiento_sup * payload.area_ha * 1000

    valor_estimado_cosecha_cop = cosecha_estimada_kg * PRECIO_LOCAL_COP_KG
    valor_estimado_cosecha_inf_cop = cosecha_estimada_inf_kg * PRECIO_LOCAL_COP_KG
    valor_estimado_cosecha_sup_cop = cosecha_estimada_sup_kg * PRECIO_LOCAL_COP_KG

    valor_cobertura_cop = valor_estimado_cosecha_cop * PORCENTAJE_COBERTURA
    valor_maximo_indemnizar_cop = get_valor_maximo_indemnizar(row, year_usado, payload.area_ha)

    departamento_usado = row.get("_departamento")

    mensaje = (
        f"Según la información climática y satelital disponible para {payload.municipio}"
        f"{' - ' + str(departamento_usado) if departamento_usado else ''}, "
        f"usando el año {year_usado}, la cosecha estimada para {payload.area_ha:.2f} hectáreas "
        f"es de {cosecha_estimada_ton:.2f} toneladas. "
        f"El intervalo estimado de producción está entre {cosecha_estimada_inf_kg:,.0f} kg "
        f"y {cosecha_estimada_sup_kg:,.0f} kg. "
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
        rendimiento_predicho=round(rendimiento_estimado, 6),
        cosecha_estimada_ton=round(cosecha_estimada_ton, 4),
        cosecha_estimada_kg=round(cosecha_estimada_kg, 2),

        rendimiento_inf=round(rendimiento_inf, 6),
        rendimiento_sup=round(rendimiento_sup, 6),
        cosecha_estimada_inf_kg=round(cosecha_estimada_inf_kg, 2),
        cosecha_estimada_sup_kg=round(cosecha_estimada_sup_kg, 2),
        valor_estimado_cosecha_inf_cop=round(valor_estimado_cosecha_inf_cop, 2),
        valor_estimado_cosecha_sup_cop=round(valor_estimado_cosecha_sup_cop, 2),

        trm_cop_usd=TRM_COP_USD,
        precio_internacional_usd_lb=PRECIO_INTERNACIONAL_USD_LB,
        precio_local_cop_kg=PRECIO_LOCAL_COP_KG,
        valor_estimado_cosecha_cop=round(valor_estimado_cosecha_cop, 2),
        porcentaje_cobertura=PORCENTAJE_COBERTURA,
        valor_cobertura_cop=round(valor_cobertura_cop, 2),
        valor_maximo_indemnizar_cop=(
            round(valor_maximo_indemnizar_cop, 2)
            if valor_maximo_indemnizar_cop is not None
            else None
        ),
        mensaje=mensaje,
    )


# -------------------------------
# Frontend estático de la solución
# -------------------------------
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

if GEOJSON_DIR.exists():
    app.mount("/geojson", StaticFiles(directory=str(GEOJSON_DIR)), name="geojson")


@app.get("/", include_in_schema=False)
def frontend_home():
    return FileResponse(str(FRONTEND_DIR / "index.html"))
