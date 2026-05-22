# Clima Café v1 — API, Frontend y Despliegue en AWS

Aplicación web para estimar la cosecha de café, visualizar el municipio del cultivo, calcular intervalos de confianza y estimar valores económicos asociados a cobertura/aseguramiento. El proyecto integra un backend en FastAPI, un frontend en HTML/CSS/JavaScript, artefactos de modelo, archivos GeoJSON y despliegue Docker en AWS EC2.

## Estado actual del proyecto

El repositorio `clima_cafe_v1` contiene:

- API productiva en FastAPI (`app.py`).
- Entrenamiento y generación de modelo (`train_model.py`).
- Frontend web (`frontend/index.html`, `frontend/app.js`, `frontend/styles.css`).
- Visualización municipal mediante archivos GeoJSON (`geojson/`).
- Login por usuarios registrados (`Data prod/usuarios_registrados.csv`).
- Despliegue mediante Docker en AWS EC2.
- Notebooks de procesamiento, revisión de variables, modelado y política/aseguramiento.
- Archivos de datos anuales, productivos y precios de referencia.
  
## Estructura general del repositorio

```text
clima_cafe_v1/
├── Artefactos/
│   ├── gb_model.pkl
│   └── rf_model.pkl
├── Data anual/
│   ├── Precio_COP.csv
│   ├── Precios.csv
│   ├── data_anual_ago_nov.xlsx
│   ├── data_anual_sep_dec.xlsx
│   ├── data_anual_total.xlsx
│   └── total_pred_final.xlsx
├── Data prod/
│   ├── usuarios_registrados.csv
│   ├── ERA5_2025_base_maestra.csv
│   ├── ERA5_base_maestra_2007_2024_transformada.csv
│   └── carpetas municipales con datos MODIS/ERA5
├── Manuales/
├── Notebooks/
│   ├── 1_procesamiento.ipynb
│   ├── 2_Revision de variables.ipynb
│   ├── 3_Modelado.ipynb
│   ├── 4_Politica.ipynb
│   └── 5_Adiciona_Registros.ipynb
├── frontend/
│   ├── app.js
│   ├── index.html
│   └── styles.css
├── geojson/
│   ├── Boyaca_Moniquira_polygons.geojson
│   ├── Boyaca_San_Jose_de_Pare_polygons.geojson
│   ├── Boyaca_Santana_polygons.geojson
│   ├── Boyaca_Togui_polygons.geojson
│   ├── Santander_Aguada_polygons.geojson
│   └── ...
├── .dockerignore
├── .gitignore
├── Dockerfile
├── README.md
├── app.py
├── deploy-clima-cafe.sh
├── requirements.txt
└── train_model.py
```

## Componentes principales

### Backend FastAPI

El archivo principal del backend es `app.py`.

Funciones principales:

- Carga datos anuales desde `Data anual/data_anual_total.xlsx`.
- Carga predicciones históricas desde `Data anual/total_pred_final.xlsx`.
- Carga precios locales desde `Data anual/Precio_COP.csv`.
- Carga precios internacionales desde `Data anual/Precios.csv`.
- Carga el modelo desde `modelos/modelo_clima_cafe.joblib`.
- Expone endpoints REST para login, salud, municipios, consulta y refresco de caché.
- Sirve el frontend desde `/static`.
- Sirve los polígonos GeoJSON desde `/geojson`.

### Frontend

El frontend está en `frontend/` e incluye:

- Pantalla inicial de login.
- Validación de usuario registrado contra `POST /login`.
- Selección de departamento y municipio.
- Visualización del polígono municipal usando archivos GeoJSON.
- Resultados estimados con intervalos de confianza.
- Cálculo de cobertura sobre valor de cosecha.
- Botón de salida para volver al login.
- Ocultamiento de municipios no disponibles en la lista desplegable.

## Login de usuarios registrados

El sistema valida el ingreso con el archivo:

```text
Data prod/usuarios_registrados.csv
```

Formato esperado:

```csv
id_usuario,estado
1036957321,activo
1019003633,activo
102892762,inactivo
1033924762,inactivo
1016544768,activo
```

Reglas:

- Solo pueden ingresar usuarios cuyo `id_usuario` exista en el archivo.
- El campo `estado` debe ser `activo`.
- Si el usuario no existe o está `inactivo`, la API retorna error `403`.
- El frontend bloquea el acceso y muestra un mensaje de usuario no autorizado.
- El backend también protege `POST /consulta`.

Ejemplo de login:

```bash
curl -X POST http://localhost:802/login \
  -H "Content-Type: application/json" \
  -d '{"numero_identidad":"1036957321"}'
```

Respuesta esperada para usuario activo:

```json
{
  "autorizado": true,
  "numero_identidad": "1036957321",
  "estado": "activo",
  "mensaje": "Usuario autorizado."
}
```

## Municipios ocultos en el frontend

El frontend oculta algunos municipios de la lista desplegable mediante una lista de exclusión en `frontend/app.js`.

Municipios ocultos actualmente:

```text
SANTANDER__AGUADA
SANTANDER__PUENTE NACIONAL
SANTANDER__VALLE DE SAN JOSÉ
BOYACA__SANTANA
```

## Visualización GeoJSON

Los polígonos municipales se encuentran en `geojson/` y la API los sirve mediante `/geojson`.

Ejemplo:

```text
http://IP_PUBLICA_EC2:802/geojson/Boyaca_Moniquira_polygons.geojson
```

El frontend carga dinámicamente el archivo correspondiente al departamento y municipio seleccionado. La visualización se hace directamente en SVG, sin depender de librerías externas.

## Flujo de cálculo

1. El usuario ingresa con número de identidad.
2. La API valida el usuario contra `Data prod/usuarios_registrados.csv`.
3. El usuario selecciona departamento, municipio, área cultivada y año.
4. El frontend envía la consulta a `POST /consulta`.
5. La API obtiene el registro del municipio/año.
6. Se usa `total_pred_final.xlsx` para recuperar el rendimiento predicho cuando está disponible.
7. Se calculan intervalos de confianza usando errores históricos positivos y negativos por municipio.
8. Se calculan:
   - rendimiento predicho,
   - intervalo de rendimiento,
   - cosecha estimada,
   - intervalo de cosecha,
   - valor estimado de cosecha,
   - intervalo del valor económico,
   - umbral de aseguramiento,
   - valor de cobertura,
   - valor máximo a indemnizar.
9. El frontend muestra resultados, mapa municipal y resumen interpretativo.

## Lógica de intervalos de confianza

La lógica proviene del notebook `Notebooks/4_Politica.ipynb`.

El cálculo toma los errores históricos por municipio:

- Promedio de errores positivos.
- Promedio de errores negativos.

Luego construye el intervalo alrededor del rendimiento predicho:

```text
rendimiento_inf = rendimiento_predicho + error_negativo_promedio
rendimiento_sup = rendimiento_predicho + error_positivo_promedio
```

A partir de ese intervalo también se calculan intervalos para producción estimada, sacos equivalentes y valor estimado de cosecha.

## Cobertura y aseguramiento

La cobertura ya no es un porcentaje fijo. La lógica actual calcula el valor de apoyo con base en la diferencia entre el valor económico asociado al umbral de aseguramiento y el valor económico de la cosecha estimada.

Condición principal:

```text
Si rendimiento_predicho < umbral_aseguramiento:
    el cultivo es elegible para apoyo
Si rendimiento_predicho >= umbral_aseguramiento:
    el cultivo no es elegible
```

El frontend muestra:

```text
Cobertura sobre valor de cosecha = valor_cobertura_cop / valor_estimado_cosecha_cop
```

Si no hay elegibilidad:

```text
valor_cobertura_cop = 0
Cobertura sobre valor de cosecha = 0.00%
```

## Endpoints disponibles

### `GET /health`

Verifica estado de aplicación, archivos cargados, modelo, datos y usuarios.

```bash
curl http://localhost:802/health
```

Debe incluir campos como:

```json
{
  "status": "ok",
  "app": "API Clima Café",
  "geojson_exists": true,
  "usuarios_file_exists": true,
  "rows_usuarios": 5
}
```

### `POST /login`

Valida el ingreso del usuario.

```bash
curl -X POST http://localhost:802/login \
  -H "Content-Type: application/json" \
  -d '{"numero_identidad":"1036957321"}'
```

### `GET /municipios`

Lista municipios y años disponibles para consulta.

```bash
curl http://localhost:802/municipios
```

### `POST /consulta`

Calcula la estimación para un cultivo.

```bash
curl -X POST http://localhost:802/consulta \
  -H "Content-Type: application/json" \
  -d '{
    "numero_identidad": "1036957321",
    "municipio": "Moniquira",
    "departamento": "Boyaca",
    "area_ha": 10,
    "year": 2024
  }'
```

### `POST /cache/refresh`

Limpia y recarga cachés internos de la API.

```bash
curl -X POST http://localhost:802/cache/refresh
```

## Payload de consulta

```json
{
  "numero_identidad": "1036957321",
  "municipio": "Moniquira",
  "departamento": "Boyaca",
  "area_ha": 10,
  "year": 2024
}
```

Campo opcional:

```json
{
  "precio_referencia_cop_125kg": 2380.22
}
```

Si no se envía `precio_referencia_cop_125kg`, la API usa el promedio local de cosecha calculado desde `Data anual/Precio_COP.csv`.

## Variables y archivos clave

| Variable / archivo | Uso |
|---|---|
| `Data anual/data_anual_total.xlsx` | Base principal para entrenamiento/modelo |
| `Data anual/total_pred_final.xlsx` | Predicciones históricas y errores para intervalos |
| `Data anual/Precio_COP.csv` | Precio local COP por carga de 125 kg |
| `Data anual/Precios.csv` | Precios internacionales |
| `Data prod/usuarios_registrados.csv` | Usuarios autorizados para login |
| `geojson/*.geojson` | Polígonos municipales |
| `modelos/modelo_clima_cafe.joblib` | Modelo entrenado usado por la API |
| `frontend/app.js` | Lógica de login, consulta, mapa y resultados |
| `Dockerfile` | Construcción de imagen productiva |

## Dockerfile

El `Dockerfile` debe copiar explícitamente las carpetas necesarias:

```dockerfile
COPY train_model.py .
COPY app.py .
COPY frontend/ frontend/
COPY geojson/ geojson/
COPY ["Data anual/", "Data anual/"]
COPY ["Data prod/", "Data prod/"]
```

La línea de `Data prod` es obligatoria para que el login funcione dentro del contenedor.

Si falta, el contenedor falla al iniciar con un error como:

```text
FileNotFoundError: No existe USUARIOS_FILE: /app/Data prod/usuarios_registrados.csv
```

## `.dockerignore`

Verificar que `.dockerignore` no excluya:

```text
Data prod
Data prod/
*.csv
usuarios_registrados.csv
geojson
geojson/
```

## Despliegue en AWS EC2

### 1. Conectarse a la instancia

```bash
ssh -i "C:\Users\jp_be\Downloads\aws_clima.pem" ec2-user@IP_PUBLICA_EC2
```

Ejemplo usado durante el despliegue:

```bash
ssh -i "C:\Users\jp_be\Downloads\aws_clima.pem" ec2-user@54.175.83.229
```

### 2. Entrar al proyecto

```bash
cd ~/clima_cafe_v1
```

### 3. Bajar cambios desde GitHub

```bash
git pull origin main
```

### 4. Construir la imagen Docker

```bash
docker build -t clima-cafe-api .
```

Reconstrucción completa sin caché:

```bash
docker build --no-cache -t clima-cafe-api .
```

### 5. Reiniciar el contenedor

```bash
docker stop clima-cafe-api
docker rm clima-cafe-api
docker run -d --name clima-cafe-api -p 802:802 clima-cafe-api
```

### 6. Verificar

```bash
docker ps
docker logs clima-cafe-api
curl http://localhost:802/health
```

Debe verse el puerto:

```text
0.0.0.0:802->802/tcp
```

## Pruebas en navegador

Aplicación:

```text
http://IP_PUBLICA_EC2:802
```

Documentación interactiva:

```text
http://IP_PUBLICA_EC2:802/docs
```

GeoJSON directo:

```text
http://IP_PUBLICA_EC2:802/geojson/Boyaca_Moniquira_polygons.geojson
```

## Pruebas recomendadas

### Usuario activo

```text
1036957321
```

Debe permitir acceso.

### Usuario inactivo

```text
1033924762
```

Debe bloquear acceso.

### Usuario inexistente

```text
999999999
```

Debe bloquear acceso con error `403`.

## Actualización desde equipo local

Cada cambio debe subirse a GitHub antes de actualizar AWS.

```bash
cd C:\proyectos\clima_cafe_v1
git status
git add app.py Dockerfile frontend/index.html frontend/app.js frontend/styles.css
git add "Data prod/usuarios_registrados.csv"
git commit -m "Actualizar aplicacion clima cafe"
git pull --rebase origin main
git push origin main
```

Luego en AWS:

```bash
cd ~/clima_cafe_v1
git pull origin main
docker build -t clima-cafe-api .
docker stop clima-cafe-api
docker rm clima-cafe-api
docker run -d --name clima-cafe-api -p 802:802 clima-cafe-api
```

## Reproducción end-to-end del experimento

El proceso experimental del proyecto se reproduce mediante los notebooks ubicados en `Notebooks/`.

Orden recomendado:

1. `Notebooks/1_procesamiento.ipynb`  
   Carga, integración y limpieza inicial de datos climáticos, satelitales y productivos.

2. `Notebooks/2_Revision de variables.ipynb`  
   Revisión exploratoria, validación de consistencia y análisis de variables.

3. `Notebooks/3_Modelado.ipynb`  
   Entrenamiento del modelo, evaluación de métricas y generación de artefactos.

4. `Notebooks/4_Politica.ipynb`  
   Cálculo de lógica de aseguramiento, umbrales, intervalos de confianza y valores económicos.

5. `Notebooks/5_Adiciona_Registros.ipynb`  
   Adición o actualización de registros para predicción/operación.

## Entrenamiento del modelo

El modelo puede reproducirse con:

```bash
python train_model.py
```

Este script:

1. Lee `Data anual/data_anual_total.xlsx`.
2. Replica la función `carga_info`.
3. Entrena el modelo.
4. Guarda el artefacto en `modelos/modelo_clima_cafe.joblib`.

## Consideraciones importantes

- El puerto productivo usado por la API es `802`.
- El grupo de seguridad de AWS debe permitir entrada al puerto `802`.
- Los nombres de archivos son sensibles a mayúsculas, acentos y errores tipográficos dentro de Linux/Docker.
- El archivo debe llamarse exactamente:

```text
Data prod/usuarios_registrados.csv
```

No:

```text
Data prod/usarios_registrados.csv
```

- Si el contenedor se apaga inmediatamente, revisar:

```bash
docker ps -a
docker logs clima-cafe-api
```

- Si `/geojson/...` retorna `404`, revisar que `Dockerfile` copie `geojson/`.
- Si `/login` falla por archivo inexistente, revisar que `Dockerfile` copie `Data prod/`.

## Licencia y uso

Proyecto desarrollado como prueba de concepto para estimación de cosecha, visualización territorial y lógica de cobertura asociada a cultivos de café.


```text
Data anual/data_anual_total.xlsx
