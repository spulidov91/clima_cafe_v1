const API_BASE = window.location.origin;

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
    mostrarErrorCampo("departamento", "Ingresa el departamento.");
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

function normalizarMunicipioDepartamento(valor) {
  if (!valor || typeof valor !== "string") {
    return {
      municipio: "",
      departamento: "SANTANDER",
      etiqueta: ""
    };
  }

  const limpio = valor.trim();

  if (limpio.includes("_")) {
    const partes = limpio.split("_");
    const departamento = partes.pop();
    const municipio = partes.join("_");

    return {
      municipio: municipio,
      departamento: departamento,
      etiqueta: `${municipio} - ${departamento}`
    };
  }

  return {
    municipio: limpio,
    departamento: "SANTANDER",
    etiqueta: limpio
  };
}

async function cargarMunicipios() {
  const select = document.getElementById("municipio");

  try {
    const response = await fetch(`${API_BASE}/municipios`);
    const data = await response.json();

    let municipios = [];

    if (Array.isArray(data)) {
      municipios = data;
    } else if (Array.isArray(data.municipios)) {
      municipios = data.municipios;
    } else if (Array.isArray(data.data)) {
      municipios = data.data;
    }

    select.innerHTML = "";

    if (municipios.length === 0) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No se encontraron municipios";
      select.appendChild(option);
      return;
    }

    municipios.forEach((item) => {
      const option = document.createElement("option");

      let municipio = "";
      let departamento = "SANTANDER";
      let etiqueta = "";

      if (typeof item === "string") {
        const normalizado = normalizarMunicipioDepartamento(item);
        municipio = normalizado.municipio;
        departamento = normalizado.departamento;
        etiqueta = normalizado.etiqueta;
      } else {
        municipio =
          item.municipio ||
          item.Mpio ||
          item.nombre ||
          item.name ||
          "";

        departamento =
          item.departamento ||
          item.Departamento ||
          "SANTANDER";

        const normalizado = normalizarMunicipioDepartamento(municipio);

        municipio = normalizado.municipio || municipio;
        departamento = normalizado.departamento || departamento;
        etiqueta = `${municipio} - ${departamento}`;
      }

      option.value = municipio;
      option.textContent = etiqueta;
      option.dataset.departamento = departamento;

      select.appendChild(option);
    });

    const selected = select.options[select.selectedIndex];

    if (selected && selected.dataset.departamento) {
      document.getElementById("departamento").value = selected.dataset.departamento;
    }

  } catch (error) {
    console.error("Error cargando municipios:", error);
    select.innerHTML = '<option value="">Error cargando municipios</option>';
    mostrarMensaje("No fue posible cargar la lista de municipios. Revisa el estado del servicio.", true);
  }
}

document.getElementById("municipio").addEventListener("change", function () {
  const selected = this.options[this.selectedIndex];

  if (selected && selected.dataset.departamento) {
    document.getElementById("departamento").value = selected.dataset.departamento;
  }
});

document.getElementById("consultaForm").addEventListener("submit", async function (event) {
  event.preventDefault();

  const btn = document.getElementById("btnConsultar");

  const payload = {
    numero_identidad: document.getElementById("numero_identidad").value.trim(),
    municipio: document.getElementById("municipio").value.trim(),
    area_ha: Number(document.getElementById("area_ha").value),
    departamento: document.getElementById("departamento").value.trim(),
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

cargarMunicipios();
