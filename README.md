# Despliegue AWS + GitHub: API Clima Café

Estos archivos convierten el repositorio `clima_cafe_v1` en una API desplegable en AWS EC2 con Docker.

## Archivos que debes agregar en la raíz del repo

```text
clima_cafe_v1/
├── Data anual/
│   ├── data_anual_ago_nov.xlsx
│   ├── data_anual_sep_dec.xlsx
│   └── data_anual_total.xlsx
├── Notebooks/
│   ├── 1_procesamiento.ipynb
│   ├── 2_Revision de variables.ipynb
│   └── 3_Modelado.ipynb
├── app.py
├── train_model.py
├── requirements.txt
├── Dockerfile
├── .dockerignore
└── deploy-clima-cafe.sh
```

## Flujo de la solución

1. `train_model.py` toma `Data anual/data_anual_total.xlsx`.
2. Replica la función `carga_info` del notebook de modelado.
3. Entrena un `RandomForestRegressor`.
4. Guarda el artefacto en `modelos/modelo_clima_cafe.joblib`.
5. `app.py` carga el modelo y expone FastAPI en el puerto `802`.
6. Docker construye todo sin depender del equipo local.

## Endpoints

- `GET /health`
- `GET /municipios`
- `POST /consulta`
- `POST /cache/refresh`

## Payload de prueba

```json
{
  "numero_identidad": "1019000363",
  "municipio": "Barbosa",
  "departamento": "Santander",
  "area_ha": 2.5
}
```

## Comandos en EC2

```bash
sudo yum update -y
sudo yum install -y docker git
sudo service docker start
sudo usermod -a -G docker ec2-user
exit
```

Vuelve a entrar por SSH y ejecuta:

```bash
chmod +x deploy-clima-cafe.sh
./deploy-clima-cafe.sh
```

O sin clonar manualmente:

```bash
curl -o deploy-clima-cafe.sh https://raw.githubusercontent.com/spulidov91/clima_cafe_v1/main/deploy-clima-cafe.sh
chmod +x deploy-clima-cafe.sh
./deploy-clima-cafe.sh
```

## Prueba

```bash
curl http://localhost:802/health
```

Desde fuera de EC2:

```bash
curl http://IP_PUBLICA_EC2:802/health
```

Consulta:

```bash
curl -X POST http://IP_PUBLICA_EC2:802/consulta \
  -H "Content-Type: application/json" \
  -d '{
    "numero_identidad": "1019000363",
    "municipio": "Barbosa",
    "departamento": "Santander",
    "area_ha": 2.5
  }'
```

## Nota importante

El notebook `1_procesamiento.ipynb` usa rutas locales tipo `C:/Users/...`. Por eso no debe ejecutarse en EC2 tal como está. Para la POC, EC2 usa los Excel ya generados en `Data anual/`.

Para producción, se recomienda convertir `1_procesamiento.ipynb` en un script con rutas relativas o lectura desde S3.
