const API_BASE = window.location.origin;

let municipiosDisponibles = [];
let mapaMunicipio = null;
let capaMunicipio = null;

const formatterCOP = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0
});

const formatterUSD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2
});

const formatterNumber = new Intl.NumberFormat("es-CO", {
  maximumFractionDigits: 2
});

function setText(id, value) {
  const element = document.getElementById(id);
  if (!element) return;
  element.textContent =
    value === null || value === undefined || value === "" ? "Pendiente" : value;
}

function getNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function pickValue(data, keys) {
  for (const key of keys) {
    if (data && data[key] !== undefined && data[key] !== null && data[key] !== "") {
      return data[key];
    }
  }
  return null;
}

function pickNumber(data, keys) {
  return getNumber(pickValue(data, keys));
}

function formatCOP(value) {
  const number = getNumber(value);
  if (number === null) return "Pendiente";
  return formatterCOP.format(number);
}

function formatUSD(value) {
  const number = getNumber(value);
  if (number === null) return "Pendiente";
  return formatterUSD.format(number);
}

function formatNumber(value) {
  const number = getNumber(value);
  if (number === null) return "Pendiente";
  return formatterNumber.format(number);
}

function formatPercent(value) {
  const number = getNumber(value);
  if (number === null) return "Pendiente";

  const percentValue = number <= 1 ? number * 100 : number;

  return `${formatNumber(percentValue)}%`;
}

function formatWithUnit(value, unit) {
  const number = getNumber(value);
  if (number === null) return "Pendiente";
  return `${formatNumber(number)} ${unit}`;
}

function formatInterval(lower, upper, formatter, label = "Intervalo de confianza") {
  const low = getNumber(lower);
  const high = getNumber(upper);

  if (low === null || high === null) {
    return `${label}: pendiente`;
  }

  return `${label}: ${formatter(low)} – ${formatter(high)}`;
}

function mostrarMensaje(texto, esError = false) {
  const mensaje = document.getElementById("mensajeResultado");
  if (!mensaje) return;
  mensaje.classList.toggle("error", esError);
  mensaje.textContent = texto;
}

function limpiarErrores() {
  [
    "numero_identidad",
    "departamento",
    "municipio",
    "area_ha",
    "year"
  ].forEach((campo) => {
    const error = document.getElementById(`error_${campo}`);
    if (error) {
      error.textContent = "";
    }
  });
}

function mostrarErrorCampo(campo, mensaje) {
  const error = document.getElementById(`error_${campo}`);
  if (error) {
    error.textContent = mensaje;
  }
}

function validarFormulario(payload) {
  limpiarErrores();

  let valido = true;

  if (!payload.numero_identidad) {
    mostrarErrorCampo("numero_identidad", "Ingresa el número de identidad.");
    valido = false;
  } else if (!/^[0-9]+$/.test(payload.numero_identidad)) {
    mostrarErrorCampo("numero_identidad", "El número de identidad debe contener solo números.");
    valido = false;
  }

  if (!payload.departamento) {
    mostrarErrorCampo("departamento", "Selecciona el departamento.");
    valido = false;
  }

  if (!payload.municipio) {
    mostrarErrorCampo("municipio", "Selecciona un municipio.");
    valido = false;
  }

  if (!payload.area_ha || payload.area_ha <= 0) {
    mostrarErrorCampo("area_ha", "Ingresa un área mayor que cero.");
    valido = false;
  }

  if (!payload.year || payload.year < 2000 || payload.year > 2100) {
    mostrarErrorCampo("year", "Ingresa un año válido.");
    valido = false;
  }

  return valido;
}

function limpiarTexto(valor) {
  return String(valor || "")
    .trim()
    .replace(/\s+/g, " ")
    .toUpperCase();
}

function removerAcentos(valor) {
  return String(valor || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

function normalizarParaArchivo(valor) {
  return removerAcentos(valor)
    .trim()
    .replace(/[^A-Za-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/_+/g, "_");
}

function titleCaseToken(token) {
  if (!token) return token;
  return token.charAt(0).toUpperCase() + token.slice(1).toLowerCase();
}

function titleCaseArchivo(valor, lowerConnectors = false) {
  const conectores = new Set(["de", "del", "la", "las", "los", "y"]);
  return normalizarParaArchivo(valor)
    .split("_")
    .filter(Boolean)
    .map((token, index) => {
      const lower = token.toLowerCase();
      if (lowerConnectors && index > 0 && conectores.has(lower)) {
        return lower;
      }
      return titleCaseToken(token);
    })
    .join("_");
}

function normalizarMunicipioDepartamento(item) {
  let municipio = "";
  let departamento = "";

  if (typeof item === "string") {
    const limpio = limpiarTexto(item);

    if (limpio.includes("_")) {
      const partes = limpio.split("_");
      departamento = limpiarTexto(partes.pop());
      municipio = limpiarTexto(partes.join("_").replace(/_/g, " "));
    } else if (limpio.includes(" - ")) {
      const partes = limpio.split(" - ");
      municipio = limpiarTexto(partes[0]);
      departamento = limpiarTexto(partes[1] || "SANTANDER");
    } else {
      municipio = limpio;
      departamento = "SANTANDER";
    }
  } else {
    municipio = limpiarTexto(
      item.municipio ||
      item.Mpio ||
      item.nombre ||
      item.name ||
      ""
    );

    departamento = limpiarTexto(
      item.departamento ||
      item.Departamento ||
      item.department ||
      "SANTANDER"
    );

    if (municipio.includes("_")) {
      const partes = municipio.split("_");
      const posibleDepartamento = limpiarTexto(partes[partes.length - 1]);

      if (!departamento || departamento === "SANTANDER") {
        departamento = posibleDepartamento;
      }

      municipio = limpiarTexto(partes.slice(0, -1).join("_").replace(/_/g, " "));
    }
  }

  return {
    municipio,
    departamento: departamento || "SANTANDER"
  };
}

function obtenerRegistrosUnicos(listaOriginal) {
  const mapa = new Map();

  listaOriginal.forEach((item) => {
    const registro = normalizarMunicipioDepartamento(item);

    if (!registro.municipio || !registro.departamento) {
      return;
    }

    const clave = `${registro.departamento}__${registro.municipio}`;

    if (!mapa.has(clave)) {
      mapa.set(clave, registro);
    }
  });

  return Array.from(mapa.values()).sort((a, b) => {
    const deptCompare = a.departamento.localeCompare(b.departamento, "es");
    if (deptCompare !== 0) return deptCompare;
    return a.municipio.localeCompare(b.municipio, "es");
  });
}

function cargarDepartamentos() {
  const selectDepartamento = document.getElementById("departamento");

  const departamentos = Array.from(
    new Set(municipiosDisponibles.map((item) => item.departamento))
  ).sort((a, b) => a.localeCompare(b, "es"));

  selectDepartamento.innerHTML = "";

  if (departamentos.length === 0) {
    selectDepartamento.innerHTML = '<option value="">No hay departamentos disponibles</option>';
    return;
  }

  departamentos.forEach((departamento) => {
    const option = document.createElement("option");
    option.value = departamento;
    option.textContent = departamento;
    selectDepartamento.appendChild(option);
  });

  if (departamentos.includes("SANTANDER")) {
    selectDepartamento.value = "SANTANDER";
  } else {
    selectDepartamento.value = departamentos[0];
  }

  cargarMunicipiosPorDepartamento(selectDepartamento.value);
}

function cargarMunicipiosPorDepartamento(departamentoSeleccionado) {
  const selectMunicipio = document.getElementById("municipio");

  const municipios = municipiosDisponibles
    .filter((item) => item.departamento === departamentoSeleccionado)
    .map((item) => item.municipio)
    .sort((a, b) => a.localeCompare(b, "es"));

  selectMunicipio.innerHTML = "";

  if (municipios.length === 0) {
    selectMunicipio.disabled = true;
    selectMunicipio.innerHTML = '<option value="">No hay municipios disponibles</option>';
    setMapInfo("Sin municipio disponible", "No hay municipios disponibles para este departamento.", "Archivo GeoJSON: pendiente");
    return;
  }

  selectMunicipio.disabled = false;

  municipios.forEach((municipio) => {
    const option = document.createElement("option");
    option.value = municipio;
    option.textContent = municipio;
    selectMunicipio.appendChild(option);
  });

  actualizarMapaMunicipio();
}

async function cargarDatosTerritoriales() {
  const selectDepartamento = document.getElementById("departamento");
  const selectMunicipio = document.getElementById("municipio");

  try {
    const response = await fetch(`${API_BASE}/municipios`);
    const data = await response.json();

    let listaOriginal = [];

    if (Array.isArray(data)) {
      listaOriginal = data;
    } else if (Array.isArray(data.municipios)) {
      listaOriginal = data.municipios;
    } else if (Array.isArray(data.data)) {
      listaOriginal = data.data;
    }

    municipiosDisponibles = obtenerRegistrosUnicos(listaOriginal);

    if (municipiosDisponibles.length === 0) {
      selectDepartamento.innerHTML = '<option value="">No hay departamentos disponibles</option>';
      selectMunicipio.innerHTML = '<option value="">No hay municipios disponibles</option>';
      selectMunicipio.disabled = true;
      mostrarMensaje("No se encontraron municipios disponibles para consultar.", true);
      setMapInfo("Sin datos territoriales", "No se encontraron municipios disponibles para cargar el mapa.", "Archivo GeoJSON: pendiente");
      return;
    }

    cargarDepartamentos();

  } catch (error) {
    console.error("Error cargando departamentos y municipios:", error);
    selectDepartamento.innerHTML = '<option value="">Error cargando departamentos</option>';
    selectMunicipio.innerHTML = '<option value="">Error cargando municipios</option>';
    selectMunicipio.disabled = true;
    mostrarMensaje("No fue posible cargar la lista de departamentos y municipios. Revisa el estado del servicio.", true);
    setMapInfo("Error cargando municipios", "No fue posible consultar el servicio de municipios.", "Archivo GeoJSON: pendiente");
  }
}

function inicializarMapa() {
  const mapElement = document.getElementById("mapaMunicipio");

  if (!mapElement || !window.L) {
    setMapInfo(
      "Mapa no disponible",
      "No se pudo cargar Leaflet. Revisa la conexión a internet o instala Leaflet localmente.",
      "Archivo GeoJSON: pendiente"
    );
    return;
  }

  mapaMunicipio = L.map("mapaMunicipio", {
    scrollWheelZoom: false
  }).setView([5.9, -73.2], 8);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors"
  }).addTo(mapaMunicipio);
}

function setMapInfo(titulo, estado, archivo) {
  setText("mapaTitulo", titulo);
  setText("mapaEstado", estado);
  setText("geojsonArchivo", archivo);
}

function construirNombresGeojson(departamento, municipio) {
  const depTitle = titleCaseArchivo(departamento, false);
  const munTitle = titleCaseArchivo(municipio, false);
  const munTitleConConectores = titleCaseArchivo(municipio, true);
  const depRaw = normalizarParaArchivo(departamento);
  const munRaw = normalizarParaArchivo(municipio);

  const nombres = [
    `${depTitle}_${munTitleConConectores}_polygons.geojson`,
    `${depTitle}_${munTitle}_polygons.geojson`,
    `${depRaw}_${munRaw}_polygons.geojson`,
    `${depRaw.toLowerCase()}_${munRaw.toLowerCase()}_polygons.geojson`
  ];

  return Array.from(new Set(nombres));
}

function construirRutasGeojson(departamento, municipio) {
  const nombres = construirNombresGeojson(departamento, municipio);
  const bases = [
    "/geojson",
    "/static/geojson",
    "./geojson",
    "../geojson"
  ];

  const rutas = [];

  nombres.forEach((nombre) => {
    bases.forEach((base) => {
      rutas.push(`${base}/${nombre}`);
    });
  });

  return rutas;
}

async function cargarPrimerGeojsonDisponible(rutas) {
  for (const ruta of rutas) {
    try {
      const response = await fetch(ruta, { cache: "no-cache" });
      if (!response.ok) continue;

      const geojson = await response.json();
      return { geojson, ruta };
    } catch (error) {
      console.warn(`No se pudo cargar ${ruta}`, error);
    }
  }

  return null;
}

function limpiarCapaMunicipio() {
  if (capaMunicipio && mapaMunicipio) {
    mapaMunicipio.removeLayer(capaMunicipio);
  }
  capaMunicipio = null;
}

async function actualizarMapaMunicipio() {
  const departamento = document.getElementById("departamento")?.value;
  const municipio = document.getElementById("municipio")?.value;

  limpiarCapaMunicipio();

  if (!departamento || !municipio) {
    setMapInfo("Selecciona un municipio", "Cuando selecciones departamento y municipio, se cargará el polígono desde la carpeta geojson.", "Archivo GeoJSON: pendiente");
    return;
  }

  setMapInfo(
    `${municipio}, ${departamento}`,
    "Cargando polígono territorial...",
    "Archivo GeoJSON: buscando archivo compatible"
  );

  if (!mapaMunicipio || !window.L) {
    setMapInfo(
      `${municipio}, ${departamento}`,
      "El municipio fue seleccionado, pero el mapa no está disponible porque Leaflet no cargó.",
      "Archivo GeoJSON: pendiente"
    );
    return;
  }

  const rutas = construirRutasGeojson(departamento, municipio);
  const resultado = await cargarPrimerGeojsonDisponible(rutas);

  if (!resultado) {
    setMapInfo(
      `${municipio}, ${departamento}`,
      "No se encontró el archivo GeoJSON del municipio. Verifica que la carpeta geojson esté disponible públicamente y que el nombre del archivo coincida.",
      `Archivo GeoJSON esperado: ${construirNombresGeojson(departamento, municipio)[0]}`
    );
    return;
  }

  capaMunicipio = L.geoJSON(resultado.geojson, {
    style: {
      color: "#14532d",
      weight: 2,
      opacity: 0.9,
      fillColor: "#2fbf7d",
      fillOpacity: 0.45
    }
  }).addTo(mapaMunicipio);

  const bounds = capaMunicipio.getBounds();
  if (bounds.isValid()) {
    mapaMunicipio.fitBounds(bounds, { padding: [22, 22] });
  }

  setMapInfo(
    `${municipio}, ${departamento}`,
    "Polígono territorial cargado correctamente.",
    `Archivo GeoJSON: ${resultado.ruta}`
  );
}

function poblarResultados(data) {
  const precioLocalLb =
    pickNumber(data, ["precio_local_cop_lb", "Precio_local_cop_lb"]) ??
    (
      pickNumber(data, ["precio_local_cop_kg", "Precio_local_cop_kg"]) !== null
        ? pickNumber(data, ["precio_local_cop_kg", "Precio_local_cop_kg"]) / 2.20462
        : null
    );

  const rendimiento = pickNumber(data, [
    "rendimiento_predicho",
    "Rendimiento_predicho",
    "rendimiento_pred",
    "Rendimiento"
  ]);

  const rendimientoInf = pickNumber(data, ["rendimiento_inf", "Rendimiento_inf"]);
  const rendimientoSup = pickNumber(data, ["rendimiento_sup", "Rendimiento_sup"]);

  const cosechaTon = pickNumber(data, ["cosecha_estimada_ton", "produccion_estimada_ton"]);
  const cosechaKg = pickNumber(data, ["Cosecha_estimada", "cosecha_estimada_kg", "produccion_estimada_kg"]);
  const cosechaInfKg = pickNumber(data, ["Cosecha_estimada_inf", "cosecha_estimada_inf_kg", "produccion_estimada_inf_kg"]);
  const cosechaSupKg = pickNumber(data, ["Cosecha_estimada_sup", "cosecha_estimada_sup_kg", "produccion_estimada_sup_kg"]);

  const valorCosecha = pickNumber(data, [
    "valor_estimado_cosecha_cop",
    "Costo_cosecha",
    "costo_cosecha",
    "valor_cosecha_cop"
  ]);
  const valorCosechaInf = pickNumber(data, [
    "costo_cosecha_lim_inf",
    "Costo_cosecha_lim_inf",
    "valor_estimado_cosecha_inf_cop",
    "valor_cosecha_inf_cop"
  ]);
  const valorCosechaSup = pickNumber(data, [
    "costo_cosecha_lim_sup",
    "Costo_cosecha_lim_sup",
    "valor_estimado_cosecha_sup_cop",
    "valor_cosecha_sup_cop"
  ]);

  const valorCobertura = pickNumber(data, [
    "valor_cobertura_cop",
    "Valor_asegurado",
    "valor_asegurado",
    "valor_estimado_cobertura_cop"
  ]);

  const valorMaxIndemnizar = pickNumber(data, [
    "Valor_max_indemnizar",
    "valor_max_indemnizar",
    "valor_maximo_indemnizar_cop"
  ]);

  setText("trm", pickNumber(data, ["trm_cop_usd", "TRM"]) !== null ? formatCOP(pickNumber(data, ["trm_cop_usd", "TRM"])) : "Pendiente de consulta");
  setText("precioInternacional", pickNumber(data, ["precio_internacional_usd_lb", "Precio_internacional_usd_lb"]) !== null ? formatUSD(pickNumber(data, ["precio_internacional_usd_lb", "Precio_internacional_usd_lb"])) : "Pendiente de consulta");
  setText("precioLocal", precioLocalLb !== null ? `${formatCOP(precioLocalLb)} / lb` : "Pendiente de consulta");

  setText("tipoRespuesta", "Consulta exitosa");
  setText("rendimientoPredicho", rendimiento !== null ? `${formatNumber(rendimiento)} ton/ha` : "Pendiente");
  setText("intervaloRendimiento", formatInterval(rendimientoInf, rendimientoSup, (value) => `${formatNumber(value)} ton/ha`));

  if (cosechaKg !== null) {
    setText("cosechaEstimada", `${formatNumber(cosechaKg)} kg`);
  } else if (cosechaTon !== null) {
    setText("cosechaEstimada", `${formatNumber(cosechaTon)} ton`);
  } else {
    setText("cosechaEstimada", "Pendiente");
  }

  setText("intervaloCosecha", formatInterval(cosechaInfKg, cosechaSupKg, (value) => `${formatNumber(value)} kg`));
  setText("valorCosecha", valorCosecha !== null ? formatCOP(valorCosecha) : "Pendiente");
  setText("intervaloValorCosecha", formatInterval(valorCosechaInf, valorCosechaSup, formatCOP));
  setText("porcentajeCobertura", pickValue(data, ["porcentaje_cobertura", "Porcentaje_cobertura"]) !== null ? formatPercent(pickValue(data, ["porcentaje_cobertura", "Porcentaje_cobertura"])) : "Pendiente");
  setText("valorCobertura", valorCobertura !== null ? formatCOP(valorCobertura) : "Pendiente");
  setText("valorMaxIndemnizar", valorMaxIndemnizar !== null ? formatCOP(valorMaxIndemnizar) : "Pendiente");
}

document.getElementById("departamento").addEventListener("change", function () {
  cargarMunicipiosPorDepartamento(this.value);
});

document.getElementById("municipio").addEventListener("change", function () {
  actualizarMapaMunicipio();
});

document.getElementById("consultaForm").addEventListener("submit", async function (event) {
  event.preventDefault();

  const btn = document.getElementById("btnConsultar");

  const payload = {
    numero_identidad: document.getElementById("numero_identidad").value.trim(),
    departamento: document.getElementById("departamento").value.trim(),
    municipio: document.getElementById("municipio").value.trim(),
    area_ha: Number(document.getElementById("area_ha").value),
    year: Number(document.getElementById("year").value)
  };

  if (!validarFormulario(payload)) {
    mostrarMensaje("Por favor revisa los campos marcados antes de calcular la estimación.", true);
    return;
  }

  btn.disabled = true;
  btn.textContent = "Calculando tu estimación...";
  mostrarMensaje("Estamos procesando la información de tu cultivo. En unos segundos verás el resultado.");

  try {
    const response = await fetch(`${API_BASE}/consulta`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok) {
      setText("tipoRespuesta", "No procesada");
      mostrarMensaje(
        data.detail
          ? `No fue posible procesar la consulta: ${JSON.stringify(data.detail)}`
          : "No fue posible procesar la consulta. Revisa los datos ingresados.",
        true
      );
      return;
    }

    poblarResultados(data);
    actualizarMapaMunicipio();

    mostrarMensaje(
      data.mensaje ??
      "Consulta realizada correctamente. Ya puedes ver la producción estimada, sus intervalos de confianza, el valor de cobertura y el mapa del municipio."
    );

  } catch (error) {
    console.error("Error consultando el servicio:", error);
    setText("tipoRespuesta", "Error de conexión");
    mostrarMensaje(
      "No fue posible consultar el servicio. Revisa la conexión o el estado de la aplicación.",
      true
    );
  } finally {
    btn.disabled = false;
    btn.textContent = "Quiero estimar mi cosecha";
  }
});

inicializarMapa();
cargarDatosTerritoriales();
