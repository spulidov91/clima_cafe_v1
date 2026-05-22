FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY train_model.py .
COPY app.py .
COPY frontend/ frontend/
COPY geojson/ geojson/
COPY ["Data anual/", "Data anual/"]
COPY ["Data prod/", "Data prod/"]

# Entrena el modelo durante la construcción de la imagen.
# Requiere que Data anual/data_anual_total.xlsx exista en el repositorio.
RUN python train_model.py \
    --data-file "Data anual/data_anual_total.xlsx" \
    --output-dir modelos \
    --exclude-year 2024

ENV DATA_FILE="Data anual/data_anual_total.xlsx"
ENV MODEL_FILE="modelos/modelo_clima_cafe.joblib"
ENV TRM_COP_USD="3650"
ENV PRECIO_INTERNACIONAL_USD_LB="3.30"
ENV PRECIO_LOCAL_COP_KG="12500"
ENV PORCENTAJE_COBERTURA="0.15"

EXPOSE 802

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "802"]
