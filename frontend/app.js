const API_BASE = window.location.origin;

let municipiosDisponibles = [];

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
  document.getElementById(id).textContent =
    value === null || value === undefined || value === "" ? "Pendiente" : value;
}

function formatCOP(value) {
  if (value === null || value === undefined || isNaN(Number(value))) {
    return "Pendiente";
  }
  return formatterCOP.format(Number(value));
}

function formatUSD(value) {
  if (value === null || value === undefined || isNaN(Number(value))) {
    return "Pendiente";
  }
  return formatterUSD.format(Number(value));
}

function formatNumber(value) {
  if (value === null || value === undefined || isNaN(Number(value))) {
    return "Pendiente";
  }
  return formatterNumber.format(Number(value));
}

function formatPercent(value) {
  if (value === null || value === undefined || isNaN(Number(value))) {
    return "Pendiente";
  }

  const numericValue = Number(value);
  const percentValue = numericValue <= 1 ? numericValue * 100 : numericValue;

  return `${formatNumber(percentValue)}%`;
}

function mostrarMensaje(texto, esError = false) {
  const mensaje = document.getElementById("mensajeResultado");
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
    return;
  }

  selectMunicipio.disabled = false;

  municipios.forEach((municipio) => {
    const option = document.createElement("option");
    option.value = municipio;
    option.textContent = municipio;
    selectMunicipio.appendChild(option);
  });
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
      return;
    }

    cargarDepartamentos();

  } catch (error) {
    console.error("Error cargando departamentos y municipios:", error);
    selectDepartamento.innerHTML = '<option value="">Error cargando departamentos</option>';
    selectMunicipio.innerHTML = '<option value="">Error cargando municipios</option>';
    selectMunicipio.disabled = true;
    mostrarMensaje("No fue posible cargar la lista de departamentos y municipios. Revisa el estado del servicio.", true);
  }
}

document.getElementById("departamento").addEventListener("change", function () {
  cargarMunicipiosPorDepartamento(this.value);
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

    const precioLocalLb =
      data.precio_local_cop_lb ??
      (
        data.precio_local_cop_kg
          ? Number(data.precio_local_cop_kg) / 2.20462
          : null
      );

    setText("trm", data.trm_cop_usd ? formatCOP(data.trm_cop_usd) : "Pendiente de consulta");
    setText("precioInternacional", data.precio_internacional_usd_lb ? formatUSD(data.precio_internacional_usd_lb) : "Pendiente de consulta");
    setText("precioLocal", precioLocalLb ? `${formatCOP(precioLocalLb)} / lb` : "Pendiente de consulta");

    setText("tipoRespuesta", "Consulta exitosa");
    setText("cosechaEstimada", data.cosecha_estimada_ton ? `${formatNumber(data.cosecha_estimada_ton)} ton` : "Pendiente");
    setText("valorCosecha", data.valor_estimado_cosecha_cop ? formatCOP(data.valor_estimado_cosecha_cop) : "Pendiente");
    setText("porcentajeCobertura", data.porcentaje_cobertura !== undefined ? formatPercent(data.porcentaje_cobertura) : "Pendiente");
    setText("valorCobertura", data.valor_cobertura_cop ? formatCOP(data.valor_cobertura_cop) : "Pendiente");

    mostrarMensaje(
      data.mensaje ??
      "Consulta realizada correctamente. Ya puedes ver una proyección de producción y el valor estimado de cobertura para tu cultivo."
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

cargarDatosTerritoriales();
