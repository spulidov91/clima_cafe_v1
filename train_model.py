import argparse
import json
from pathlib import Path
from typing import Dict, Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


SEED = 27
TARGET = "Rendimiento"

FEATS_SELECT_TOTAL = [
    "EVI_Avg_Mean_deviation",
    "ssrd_mean",
    "ssrd_std",
    "EVI_Median_Median",
    "d2m_std",
    "e_std",
    "NDVI_Avg_Mean_deviation",
    "stl1_std",
    "tp_std",
    "NDVI_Max_Maximum",
    "tp_mean",
    "EVI_Max_Maximum",
    "Flag_covid",
    "Mpio",
]

DROP_COLS = [
    "Municipio",
    "Departamento",
    "EVI_Min_Date",
    "EVI_Max_Date",
    "NDVI_Min_Date",
    "NDVI_Max_Date",
    "NDVI_Max_Count",
    "Producto",
    "Área Cosechada",
    "Área Sembrada",
    "Ciclo",
    "Producción",
]


def carga_info(data: pd.DataFrame) -> pd.DataFrame:
    """
    Replica la lógica base del notebook 3_Modelado.ipynb, pero de forma segura
    para ejecución en contenedor.
    """
    data = data.copy()

    required_source_cols = {"Municipio", "Departamento", "Year"}
    missing_source = required_source_cols - set(data.columns)
    if missing_source:
        raise ValueError(f"Faltan columnas fuente requeridas: {sorted(missing_source)}")

    data["Mpio"] = (
        data["Municipio"].astype(str).str.strip()
        + "_"
        + data["Departamento"].astype(str).str.strip()
    )
    data["Flag_covid"] = np.where(data["Year"] == 2020, 1, 0)

    if "EVI_Max_Count" in data.columns:
        data = data.rename(columns={"EVI_Max_Count": "Resolucion"})

    data = data.drop(columns=[c for c in DROP_COLS if c in data.columns], errors="ignore")

    required_model_cols = ["Year", TARGET] + FEATS_SELECT_TOTAL
    missing_model = [c for c in required_model_cols if c not in data.columns]
    if missing_model:
        raise ValueError(f"Faltan columnas para modelar: {missing_model}")

    data = data[required_model_cols].copy()
    data = data.dropna(subset=required_model_cols)

    return data


def build_pipeline() -> Pipeline:
    numeric_features = [c for c in FEATS_SELECT_TOTAL if c != "Mpio"]
    categorical_features = ["Mpio"]

    try:
        encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        encoder = OneHotEncoder(handle_unknown="ignore", sparse=False)

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", "passthrough", numeric_features),
            ("cat", encoder, categorical_features),
        ],
        remainder="drop",
    )

    model = RandomForestRegressor(
        n_estimators=300,
        random_state=SEED,
        n_jobs=-1,
        min_samples_leaf=1,
    )

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", model),
        ]
    )


def train(data_file: Path, output_dir: Path, exclude_year: int | None = 2024) -> Dict[str, Any]:
    if not data_file.exists():
        raise FileNotFoundError(f"No existe el archivo de datos: {data_file}")

    raw_df = pd.read_excel(data_file)
    df = carga_info(raw_df)

    train_df = df.copy()
    oot_df = pd.DataFrame()

    if exclude_year is not None and "Year" in train_df.columns:
        oot_df = train_df[train_df["Year"] == exclude_year].copy()
        train_df = train_df[train_df["Year"] != exclude_year].copy()

    X = train_df[FEATS_SELECT_TOTAL]
    y = train_df[TARGET].astype(float)

    if len(train_df) < 10:
        raise ValueError(f"Hay muy pocos registros para entrenar: {len(train_df)}")

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.25,
        random_state=SEED,
    )

    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)

    pred_train = pipeline.predict(X_train)
    pred_test = pipeline.predict(X_test)

    metrics = {
        "rmse_train": float(np.sqrt(mean_squared_error(y_train, pred_train))),
        "rmse_test": float(np.sqrt(mean_squared_error(y_test, pred_test))),
        "rows_raw": int(len(raw_df)),
        "rows_processed": int(len(df)),
        "rows_train": int(len(train_df)),
        "rows_test": int(len(X_test)),
        "target": TARGET,
        "features": FEATS_SELECT_TOTAL,
        "exclude_year": exclude_year,
        "data_file": str(data_file),
    }

    if exclude_year is not None and len(oot_df) > 0:
        X_oot = oot_df[FEATS_SELECT_TOTAL]
        y_oot = oot_df[TARGET].astype(float)
        pred_oot = pipeline.predict(X_oot)
        metrics["rows_oot"] = int(len(oot_df))
        metrics["rmse_oot"] = float(np.sqrt(mean_squared_error(y_oot, pred_oot)))

    output_dir.mkdir(parents=True, exist_ok=True)

    artifact = {
        "pipeline": pipeline,
        "features": FEATS_SELECT_TOTAL,
        "target": TARGET,
        "metrics": metrics,
    }

    model_path = output_dir / "modelo_clima_cafe.joblib"
    metrics_path = output_dir / "metadata_modelo.json"

    joblib.dump(artifact, model_path)

    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    print(f"Modelo guardado en: {model_path}")
    print(f"Metadata guardada en: {metrics_path}")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))

    return metrics


def parse_args():
    parser = argparse.ArgumentParser(description="Entrena modelo de clima café para API.")
    parser.add_argument(
        "--data-file",
        default="Data anual/data_anual_total.xlsx",
        help="Ruta al Excel consolidado.",
    )
    parser.add_argument(
        "--output-dir",
        default="modelos",
        help="Directorio donde se guardan los artefactos del modelo.",
    )
    parser.add_argument(
        "--exclude-year",
        type=int,
        default=2024,
        help="Año que se deja como OOT. Usa 0 para no excluir ningún año.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    exclude_year = None if args.exclude_year == 0 else args.exclude_year
    train(Path(args.data_file), Path(args.output_dir), exclude_year=exclude_year)
