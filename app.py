import os
import unicodedata
from pathlib import Path
from typing import Optional, Tuple

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
MODEL_FILE = path_from_env("MODEL_FILE", "modelos/modelo_clima_cafe.joblib")
PRED_FILE = path_from_env("PRED_FILE", "Data anual/total_pred_final.xlsx")
PRECIO_COP_FILE = path_from_env("PRECIO_COP_FILE", "Data anual/Precio_COP.csv")
PRECIOS_INT_FILE = path_from_env("PRECIOS_INT_FILE", "Data anual/Precios.csv")
FRONTEND_DIR = path_from_env("FRONTEND_DIR", "frontend")
GEOJSON_DIR = path_from_env("GEOJSON_DIR", "geojson")

TRM_COP_USD = float(os.getenv("TRM_COP_USD", "3650"))
PRECIO_INTERNACIONAL_USD_LB = float(os.getenv("PRECIO_INTERNACIONAL_USD_LB", "3.30"))
PRECIO_LOCAL_COP_KG = float(os.getenv("PRECIO_LOCAL_COP_KG", "12500"))

app = FastAPI(
    title=APP_NAME,
    version="1.1.0",
    description="API para estimar cosecha de café, intervalos de confianza, aseguramiento y visualización municipal.",
)

_raw_df_cache: Optional[pd.DataFrame] = None
_processed_df_cache: Optional[pd.DataFrame] = None
_artifact_cache = None
_precios_cache: Optional[pd.DataFrame] = None
_predicciones_cache: Optional[pd.DataFrame] = None
_predicciones_stats_cache: dict[int, pd.DataFrame] = {}


class ConsultaRequest(BaseModel):
    numero_identidad: str = Field(..., examples=["1019000363"])
    municipio: str = Field(..., examples=["Santana"])
    area_ha: float = Field(..., gt=0, examples=[3.5])
    departamento: Optional[str] = Field(
        default=None,
        description="Opcional. Útil si hay municipios con el mismo nombre en varios departamentos.",
        examples=["Boyaca"],
    )
    year: Optional[int] = Field(
        default=None,
        description="Opcional. Si no se envía, se usa el año más reciente disponible para el municipio.",
        examples=[2024],
    )
    precio_referencia_cop_125kg: Optional[float] = Field(
        default=None,
        gt=0,
        description=(
            "Opcional. Precio de referencia del seguro por carga de 125 kg, en miles de COP. "
            "Si no se envía, se usa el promedio de precios locales de cosecha del año consultado."
        ),
        examples=[2380.22131147541],
    )


class ConsultaResponse(BaseModel):
    tipo_respuesta_api: int
    numero_identidad: str
    municipio: str
    departamento: Optional[str]
    mpio: str
    year_usado: int
    area_ha: float

    # Rendimiento y producción
    rendimiento_predicho: float
    rendimiento_estimado_ton_ha: float
    rendimiento_inf: Optional[float] = None
    rendimiento_sup: Optional[float] = None
    rendimiento_umbral_aseguramiento: Optional[float] = None
    rendimiento_min_historico: Optional[float] = None
    cosecha_estimada_ton: float
    cosecha_estimada_kg: float
    cosecha_estimada_sacos_125kg: float
    cosecha_estimada_inf_kg: Optional[float] = None
    cosecha_estimada_sup_kg: Optional[float] = None
    cosecha_estimada_inf_sacos_125kg: Optional[float] = None
    cosecha_estimada_sup_sacos_125kg: Optional[float] = None

    # Precios de referencia
    trm_cop_usd: float
    precio_internacional_usd_lb: float
    precio_oic_usd_lb: Optional[float] = None
    precio_nueva_york_usd_lb: Optional[float] = None
    precio_europa_usd_lb: Optional[float] = None
    precio_local_cop_125kg: Optional[float] = None
    precio_local_cop_kg: float
    precio_referencia_usado: str

    # Valores económicos
    valor_estimado_cosecha_cop: float
    valor_estimado_cosecha_inf_cop: Optional[float] = None
    valor_estimado_cosecha_sup_cop: Optional[float] = None
    valor_asegurado: float
    valor_cobertura_cop: float
    valor_max_indemnizar: float
    valor_maximo_indemnizar_cop: float
    elegible_cobertura: bool
    elegible_maxima_indemnizacion: bool
    mensaje: str


def normalize_text(value: str) -> str:
    value = "" if value is None else str(value)
    value = value.strip().lower()
    value = "".join(
        c for c in unicodedata.normalize("NFD", value)
        if unicodedata.category(c) != "Mn"
    )
    return value


def make_mpio_key(municipio: str, departamento: Optional[str]) -> str:
    municipio_key = normalize_text(municipio).upper()
    departamento_key = normalize_text(departamento or "").upper()
    municipio_key = " ".join(municipio_key.split())
    departamento_key = " ".join(departamento_key.split())
    return f"{municipio_key}_{departamento_key}" if departamento_key else municipio_key


def first_value(series: pd.Series, default=None):
    if series is None or len(series) == 0:
        return default
    value = series.iloc[0]
    if pd.isna(value):
        return default
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
    processed["_mpio_key"] = processed["Mpio"].apply(lambda x: normalize_text(x).upper())

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


def load_precios_cosecha() -> pd.DataFrame:
    """
    Replica la función carga_precios() del notebook 4.
    - Precio_COP.csv: promedio de COP_125_Kg para meses 9, 10, 11 y 12.
    - Precios.csv: promedio de precios internacionales para meses 09, 10, 11 y 12.
    """
    global _precios_cache
    if _precios_cache is not None:
        return _precios_cache

    if not PRECIO_COP_FILE.exists() or not PRECIOS_INT_FILE.exists():
        _precios_cache = pd.DataFrame()
        return _precios_cache

    precios_cop = pd.read_csv(PRECIO_COP_FILE)
    precios_cop["COP_125_Kg"] = precios_cop["COP_125_Kg"].astype(float)
    precios_cosecha_cop = (
        precios_cop[precios_cop["Mes"].isin([9, 10, 11, 12])]
        .groupby("Year")[["COP_125_Kg"]]
        .mean()
        .reset_index()
    )

    precios = pd.read_csv(PRECIOS_INT_FILE)
    precios["Year"] = precios["Fecha"].astype(str).str[:4].astype(int)
    precios["Mes"] = precios["Fecha"].astype(str).str[5:7]
    precios_cosecha = (
        precios[precios["Mes"].isin(["09", "10", "11", "12"])]
        .groupby("Year")[[
            "Precio_indicador_compuesto_OIC_US_Cents",
            "Nueva_York_US_Cents",
            "Europa_US_Cents",
        ]]
        .mean()
        .reset_index()
    )

    _precios_cache = precios_cosecha.merge(precios_cosecha_cop, on="Year", how="inner")
    return _precios_cache


def load_predicciones() -> pd.DataFrame:
    global _predicciones_cache
    if _predicciones_cache is not None:
        return _predicciones_cache

    if not PRED_FILE.exists():
        _predicciones_cache = pd.DataFrame()
        return _predicciones_cache

    pred = pd.read_excel(PRED_FILE)
    required = {"Year", "Mpio", "Rendimiento", "Rendimiento_Predicho", "Error"}
    missing = required - set(pred.columns)
    if missing:
        raise ValueError(f"Faltan columnas en {PRED_FILE}: {sorted(missing)}")

    pred["_mpio_key"] = pred["Mpio"].apply(lambda x: normalize_text(x).upper())
    _predicciones_cache = pred
    return _predicciones_cache


def carga_predicciones_intervalo(year: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Replica la función carga_predicciones_intervalo(año) del notebook 4."""
    if year in _predicciones_stats_cache:
        return load_predicciones(), _predicciones_stats_cache[year]

    predicciones = load_predicciones()
    if predicciones.empty:
        _predicciones_stats_cache[year] = pd.DataFrame()
        return predicciones, _predicciones_stats_cache[year]

    pred_sin_year = predicciones[predicciones["Year"] != year]

    pred_min = pred_sin_year.groupby("Mpio", as_index=False)["Rendimiento"].min()
    pred_min.rename(columns={"Rendimiento": "Rendimiento_min"}, inplace=True)

    pred_max = pred_sin_year.groupby("Mpio", as_index=False)["Rendimiento"].max()
    pred_max.rename(columns={"Rendimiento": "Rendimiento_max"}, inplace=True)

    pred_avg = pred_sin_year.groupby("Mpio", as_index=False)["Rendimiento"].mean()
    pred_avg.rename(columns={"Rendimiento": "Rendimiento_avg"}, inplace=True)

    std_by_mpio = predicciones.groupby("Mpio", as_index=False)["Rendimiento"].std()
    std_by_mpio.rename(columns={"Rendimiento": "Std"}, inplace=True)
    pred_avg = pred_avg.merge(std_by_mpio, on="Mpio", how="left")

    pred_avg["Std_thresh_1"] = pred_avg["Rendimiento_avg"] - pred_avg["Std"]
    pred_avg["Std_thresh_2"] = pred_avg["Rendimiento_avg"] - pred_avg["Std"] * 2

    err_pos = (
        predicciones[(predicciones["Year"] <= year) & (predicciones["Error"] > 0)]
        .groupby("Mpio", as_index=False)[["Error"]]
        .mean()
        .rename(columns={"Error": "Error_positivo"})
    )
    err_neg = (
        predicciones[(predicciones["Year"] <= year) & (predicciones["Error"] < 0)]
        .groupby("Mpio", as_index=False)[["Error"]]
        .mean()
        .rename(columns={"Error": "Error_negativo"})
    )

    pred_avg = pred_avg.merge(pred_min, on="Mpio", how="left")
    pred_avg = pred_avg.merge(pred_max, on="Mpio", how="left")
    pred_avg = pred_avg.merge(err_pos, on="Mpio", how="left")
    pred_avg = pred_avg.merge(err_neg, on="Mpio", how="left")
    pred_avg["_mpio_key"] = pred_avg["Mpio"].apply(lambda x: normalize_text(x).upper())

    _predicciones_stats_cache[year] = pred_avg
    return predicciones, pred_avg


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
            detail="No se encontró información para el municipio/departamento solicitado. Consulta GET /municipios.",
        )

    if year is not None:
        filtered = filtered[filtered["Year"] == year].copy()
        if filtered.empty:
            raise HTTPException(status_code=404, detail=f"No hay información para el año solicitado: {year}")

    filtered = filtered.sort_values("Year", ascending=False)
    return filtered.iloc[0]


def get_rendimiento_predicho(row: pd.Series, year_usado: int, pipeline) -> float:
    """
    Prioriza total_pred_final.xlsx para replicar el notebook 4.
    Si no existe coincidencia, usa el pipeline entrenado como respaldo.
    """
    predicciones = load_predicciones()
    mpio_key = normalize_text(row.get("Mpio", "")).upper()

    if not predicciones.empty:
        pred_actual = predicciones[(predicciones["_mpio_key"] == mpio_key) & (predicciones["Year"] == year_usado)]
        if not pred_actual.empty:
            return max(0.0, float(pred_actual["Rendimiento_Predicho"].iloc[0]))

    X = pd.DataFrame([row[FEATS_SELECT_TOTAL].to_dict()])
    return max(0.0, float(pipeline.predict(X)[0]))


def calcula_aseguramiento_intervalo(area_ha: float, row: pd.Series, year_usado: int, rendimiento_pred: float, precio_ref_cop_125kg: Optional[float] = None) -> dict:
    """Replica la función calcula_aseguramiento_intervalo() del notebook 4 para API."""
    mpio_key = normalize_text(row.get("Mpio", "")).upper()
    mpio_original = str(row.get("Mpio", ""))

    precios_cosecha = load_precios_cosecha()
    predicciones, stats = carga_predicciones_intervalo(year_usado)

    stat = stats[stats["_mpio_key"] == mpio_key] if not stats.empty else pd.DataFrame()
    if stat.empty:
        # Respaldo si no hay total_pred_final.xlsx o el municipio no existe allí.
        hist = load_processed_df()
        hist = hist[(hist["_mpio_norm"] == normalize_text(mpio_original)) & (hist["Year"] != year_usado)].copy()
        rendimiento_avg = float(hist[TARGET].mean()) if not hist.empty else rendimiento_pred
        rendimiento_std = float(hist[TARGET].std()) if not hist.empty else 0.0
        rendimiento_min = float(hist[TARGET].min()) if not hist.empty else rendimiento_pred
        error_neg = -float(load_artifact().get("metrics", {}).get("rmse_oot") or load_artifact().get("metrics", {}).get("rmse_test") or 0)
        error_pos = abs(error_neg)
    else:
        rendimiento_avg = float(stat["Rendimiento_avg"].iloc[0])
        rendimiento_std = float(stat["Std"].iloc[0])
        rendimiento_min = float(stat["Rendimiento_min"].iloc[0])
        error_neg = first_value(stat["Error_negativo"], 0.0)
        error_pos = first_value(stat["Error_positivo"], 0.0)
        error_neg = 0.0 if pd.isna(error_neg) else float(error_neg)
        error_pos = 0.0 if pd.isna(error_pos) else float(error_pos)

    rendimiento_umbral = round(rendimiento_avg - rendimiento_std, 4)
    rendimiento_min = round(rendimiento_min, 4)

    rendimiento_pred = round(rendimiento_pred, 4)
    rendimiento_inf = round(max(0.0, rendimiento_pred + round(error_neg, 4)), 4)
    rendimiento_sup = round(max(rendimiento_inf, rendimiento_pred + round(error_pos, 4)), 4)

    precios_year = precios_cosecha[precios_cosecha["Year"] == year_usado] if not precios_cosecha.empty else pd.DataFrame()

    if precio_ref_cop_125kg is not None:
        precio_cop_125kg = float(precio_ref_cop_125kg)
        precio_ref_usado = "usuario"
    elif not precios_year.empty:
        precio_cop_125kg = float(precios_year["COP_125_Kg"].iloc[0])
        precio_ref_usado = "promedio_cosecha_local"
    else:
        # Respaldo a COP/kg de variable de entorno, convertido a la escala del notebook.
        precio_cop_125kg = float(PRECIO_LOCAL_COP_KG * 125 / 1000)
        precio_ref_usado = "fallback_env_precio_local_cop_kg"

    precio_oic_usd_lb = None
    precio_ny_usd_lb = None
    precio_europa_usd_lb = None
    if not precios_year.empty:
        precio_oic_usd_lb = float(precios_year["Precio_indicador_compuesto_OIC_US_Cents"].iloc[0]) / 100
        precio_ny_usd_lb = float(precios_year["Nueva_York_US_Cents"].iloc[0]) / 100
        precio_europa_usd_lb = float(precios_year["Europa_US_Cents"].iloc[0]) / 100

    precio_internacional_usd_lb = precio_oic_usd_lb if precio_oic_usd_lb is not None else PRECIO_INTERNACIONAL_USD_LB
    precio_local_cop_kg = precio_cop_125kg * 1000 / 125

    # Producción: se replica el redondeo del notebook 4.
    produccion_estimada_kg = round(rendimiento_pred * area_ha, 1) * 1000
    produccion_estimada_saco = round(produccion_estimada_kg / 125)

    produccion_estimada_inf_kg = round(rendimiento_inf * area_ha, 1) * 1000
    produccion_estimada_inf_saco = round(produccion_estimada_inf_kg / 125)

    produccion_estimada_sup_kg = round(rendimiento_sup * area_ha, 1) * 1000
    produccion_estimada_sup_saco = round(produccion_estimada_sup_kg / 125)

    produccion_umbral_kg = round(rendimiento_umbral * area_ha, 4) * 1000
    produccion_umbral_saco = round(produccion_umbral_kg / 125, 4)

    produccion_min_kg = round(rendimiento_min * area_ha, 4) * 1000
    produccion_min_saco = round(produccion_min_kg / 125, 4)

    # Costos: se replica la escala del notebook: sacos * 1000 * COP_125_Kg.
    costo_cosecha = round(produccion_estimada_saco * 1000) * precio_cop_125kg
    costo_cosecha_lim_inf = round(produccion_estimada_inf_saco * 1000) * precio_cop_125kg
    costo_cosecha_lim_sup = round(produccion_estimada_sup_saco * 1000) * precio_cop_125kg

    costo_cosecha_thresh = round(produccion_umbral_saco * 1000) * precio_cop_125kg
    costo_cosecha_min = round(produccion_min_saco * 1000) * precio_cop_125kg

    valor_asegurado = costo_cosecha_thresh - costo_cosecha
    valor_max_indemnizar = costo_cosecha_thresh - costo_cosecha_min

    elegible = rendimiento_pred < rendimiento_umbral
    elegible_maxima = elegible and rendimiento_pred <= rendimiento_min

    return {
        "mpio": mpio_original,
        "rendimiento_predicho": rendimiento_pred,
        "rendimiento_inf": rendimiento_inf,
        "rendimiento_sup": rendimiento_sup,
        "rendimiento_umbral_aseguramiento": rendimiento_umbral,
        "rendimiento_min_historico": rendimiento_min,
        "cosecha_estimada_kg": produccion_estimada_kg,
        "cosecha_estimada_sacos_125kg": float(produccion_estimada_saco),
        "cosecha_estimada_inf_kg": produccion_estimada_inf_kg,
        "cosecha_estimada_sup_kg": produccion_estimada_sup_kg,
        "cosecha_estimada_inf_sacos_125kg": float(produccion_estimada_inf_saco),
        "cosecha_estimada_sup_sacos_125kg": float(produccion_estimada_sup_saco),
        "precio_local_cop_125kg": precio_cop_125kg,
        "precio_local_cop_kg": precio_local_cop_kg,
        "precio_internacional_usd_lb": precio_internacional_usd_lb,
        "precio_oic_usd_lb": precio_oic_usd_lb,
        "precio_nueva_york_usd_lb": precio_ny_usd_lb,
        "precio_europa_usd_lb": precio_europa_usd_lb,
        "precio_referencia_usado": precio_ref_usado,
        "Costo_cosecha": costo_cosecha,
        "costo_cosecha_lim_inf": costo_cosecha_lim_inf,
        "costo_cosecha_lim_sup": costo_cosecha_lim_sup,
        "Valor_asegurado": valor_asegurado,
        "Valor_max_indemnizar": valor_max_indemnizar,
        "elegible_cobertura": elegible,
        "elegible_maxima_indemnizacion": elegible_maxima,
    }


@app.on_event("startup")
def startup_event():
    load_raw_df()
    load_processed_df()
    load_artifact()
    load_precios_cosecha()
    load_predicciones()


@app.get("/health")
def health():
    raw_df = load_raw_df()
    processed_df = load_processed_df()
    artifact = load_artifact()
    pred_df = load_predicciones()
    precios = load_precios_cosecha()

    return {
        "status": "ok",
        "app": APP_NAME,
        "data_file": str(DATA_FILE),
        "model_file": str(MODEL_FILE),
        "pred_file": str(PRED_FILE),
        "precio_cop_file": str(PRECIO_COP_FILE),
        "precios_int_file": str(PRECIOS_INT_FILE),
        "frontend_dir": str(FRONTEND_DIR),
        "geojson_dir": str(GEOJSON_DIR),
        "geojson_exists": GEOJSON_DIR.exists(),
        "rows_raw": len(raw_df),
        "rows_processed": len(processed_df),
        "rows_predictions": len(pred_df),
        "rows_precios": len(precios),
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
    global _raw_df_cache, _processed_df_cache, _artifact_cache, _precios_cache, _predicciones_cache, _predicciones_stats_cache
    _raw_df_cache = None
    _processed_df_cache = None
    _artifact_cache = None
    _precios_cache = None
    _predicciones_cache = None
    _predicciones_stats_cache = {}
    return health()


@app.post("/consulta", response_model=ConsultaResponse)
def consulta(payload: ConsultaRequest):
    artifact = load_artifact()
    pipeline = artifact["pipeline"]

    row = get_model_row(payload.municipio, payload.departamento, payload.year)
    year_usado = int(row["Year"])
    departamento_usado = row.get("_departamento")

    rendimiento_pred = get_rendimiento_predicho(row, year_usado, pipeline)
    calculos = calcula_aseguramiento_intervalo(
        area_ha=payload.area_ha,
        row=row,
        year_usado=year_usado,
        rendimiento_pred=rendimiento_pred,
        precio_ref_cop_125kg=payload.precio_referencia_cop_125kg,
    )

    cosecha_estimada_ton = calculos["cosecha_estimada_kg"] / 1000
    valor_cobertura_cop = max(0.0, calculos["Valor_asegurado"])
    valor_max_indemnizar = max(0.0, calculos["Valor_max_indemnizar"])

    if calculos["elegible_maxima_indemnizacion"]:
        estado = "es elegible para recibir la máxima compensación"
    elif calculos["elegible_cobertura"]:
        estado = "es elegible para recibir apoyo"
    else:
        estado = "no es elegible para recibir apoyo"

    mensaje = (
        f"Según la información climática y satelital disponible para {payload.municipio}"
        f"{' - ' + str(departamento_usado) if departamento_usado else ''}, usando el año {year_usado}, "
        f"el rendimiento predicho es {calculos['rendimiento_predicho']:.4f} ton/ha "
        f"con intervalo [{calculos['rendimiento_inf']:.4f}, {calculos['rendimiento_sup']:.4f}] ton/ha. "
        f"La cosecha estimada para {payload.area_ha:.2f} hectáreas es {calculos['cosecha_estimada_kg']:,.0f} kg "
        f"con intervalo [{calculos['cosecha_estimada_inf_kg']:,.0f}, {calculos['cosecha_estimada_sup_kg']:,.0f}] kg. "
        f"El valor estimado de la cosecha es {calculos['Costo_cosecha']:,.0f} COP "
        f"con intervalo [{calculos['costo_cosecha_lim_inf']:,.0f}, {calculos['costo_cosecha_lim_sup']:,.0f}] COP. "
        f"Con el umbral de aseguramiento {calculos['rendimiento_umbral_aseguramiento']:.4f} ton/ha, el cultivo {estado}."
    )

    return ConsultaResponse(
        tipo_respuesta_api=200,
        numero_identidad=payload.numero_identidad,
        municipio=payload.municipio,
        departamento=str(departamento_usado) if departamento_usado is not None else payload.departamento,
        mpio=str(row.get("Mpio", make_mpio_key(payload.municipio, payload.departamento))),
        year_usado=year_usado,
        area_ha=round(payload.area_ha, 4),

        rendimiento_predicho=calculos["rendimiento_predicho"],
        rendimiento_estimado_ton_ha=calculos["rendimiento_predicho"],
        rendimiento_inf=calculos["rendimiento_inf"],
        rendimiento_sup=calculos["rendimiento_sup"],
        rendimiento_umbral_aseguramiento=calculos["rendimiento_umbral_aseguramiento"],
        rendimiento_min_historico=calculos["rendimiento_min_historico"],
        cosecha_estimada_ton=round(cosecha_estimada_ton, 4),
        cosecha_estimada_kg=round(calculos["cosecha_estimada_kg"], 2),
        cosecha_estimada_sacos_125kg=round(calculos["cosecha_estimada_sacos_125kg"], 2),
        cosecha_estimada_inf_kg=round(calculos["cosecha_estimada_inf_kg"], 2),
        cosecha_estimada_sup_kg=round(calculos["cosecha_estimada_sup_kg"], 2),
        cosecha_estimada_inf_sacos_125kg=round(calculos["cosecha_estimada_inf_sacos_125kg"], 2),
        cosecha_estimada_sup_sacos_125kg=round(calculos["cosecha_estimada_sup_sacos_125kg"], 2),

        trm_cop_usd=TRM_COP_USD,
        precio_internacional_usd_lb=round(calculos["precio_internacional_usd_lb"], 6),
        precio_oic_usd_lb=round(calculos["precio_oic_usd_lb"], 6) if calculos["precio_oic_usd_lb"] is not None else None,
        precio_nueva_york_usd_lb=round(calculos["precio_nueva_york_usd_lb"], 6) if calculos["precio_nueva_york_usd_lb"] is not None else None,
        precio_europa_usd_lb=round(calculos["precio_europa_usd_lb"], 6) if calculos["precio_europa_usd_lb"] is not None else None,
        precio_local_cop_125kg=round(calculos["precio_local_cop_125kg"], 6),
        precio_local_cop_kg=round(calculos["precio_local_cop_kg"], 6),
        precio_referencia_usado=calculos["precio_referencia_usado"],

        valor_estimado_cosecha_cop=round(calculos["Costo_cosecha"], 2),
        valor_estimado_cosecha_inf_cop=round(calculos["costo_cosecha_lim_inf"], 2),
        valor_estimado_cosecha_sup_cop=round(calculos["costo_cosecha_lim_sup"], 2),
        valor_asegurado=round(calculos["Valor_asegurado"], 2),
        valor_cobertura_cop=round(valor_cobertura_cop, 2),
        valor_max_indemnizar=round(valor_max_indemnizar, 2),
        valor_maximo_indemnizar_cop=round(valor_max_indemnizar, 2),
        elegible_cobertura=calculos["elegible_cobertura"],
        elegible_maxima_indemnizacion=calculos["elegible_maxima_indemnizacion"],
        mensaje=mensaje,
    )


# -------------------------------
# Frontend estático y GeoJSON
# -------------------------------
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

if GEOJSON_DIR.exists():
    app.mount("/geojson", StaticFiles(directory=str(GEOJSON_DIR)), name="geojson")


@app.get("/", include_in_schema=False)
def frontend_home():
    return FileResponse(str(FRONTEND_DIR / "index.html"))
