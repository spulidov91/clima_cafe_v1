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
    value === null || value === undefined || value === "" ? "--" : value;
}

function formatCOP(value) {
  if (value === null || value === undefined || isNaN(Number(value))) {
    return "--";
  }
  return formatterCOP.format(Number(value));
}

function formatUSD(value) {
  if (value === null || value === undefined || isNaN(Number(value))) {
    return "--";
  }
  return formatterUSD.format(Number(value));
}

function formatNumber(value) {
  if (value === null || value === undefined || isNaN(Number(value))) {
    return "--";
  }
  return formatterNumber.format(Number(value));
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

      if (typeof item === "string") {
        option.value = item;
        option.textContent = item;
      } else {
        const nombre =
          item.municipio ||
          item.Mpio ||
          item.nombre ||
          item.name ||
          JSON.stringify(item);

        const departamento =
          item.departamento ||
          item.Departamento ||
          "Santander";

        option.value = nombre;
        option.textContent = nombre;
        option.dataset.departamento = departamento;
      }

      select.appendChild(option);
    });
  } catch (error) {
    console.error("Error cargando municipios:", error);
    select.innerHTML = '<option value="">Error cargando municipios</option>';
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
  const mensaje = document.getElementById("mensajeResultado");

  btn.disabled = true;
  btn.textContent = "Consultando...";
  mensaje.classList.remove("error");
  mensaje.textContent = "Consultando la API, por favor espere...";

  const payload = {
    numero_identidad: document.getElementById("numero_identidad").value.trim(),
    municipio: document.getElementById("municipio").value,
    area_ha: Number(document.getElementById("area_ha").value),
    departamento: document.getElementById("departamento").value.trim(),
    year: Number(document.getElementById("year").value)
  };

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
      mensaje.classList.add("error");
      mensaje.textContent = data.detail
        ? JSON.stringify(data.detail)
        : "La API retornó un error en la consulta.";
      return;
    }

    const precioLocalLb =
      data.precio_local_cop_lb ??
      (
        data.precio_local_cop_kg
          ? Number(data.precio_local_cop_kg) / 2.20462
          : null
      );

    setText("trm", data.trm_cop_usd ? formatCOP(data.trm_cop_usd) : "--");
    setText("precioInternacional", data.precio_internacional_usd_lb ? formatUSD(data.precio_internacional_usd_lb) : "--");
    setText("precioLocal", precioLocalLb ? `${formatCOP(precioLocalLb)} / lb` : "--");

    setText("tipoRespuesta", data.tipo_respuesta_api ?? response.status);
    setText("cosechaEstimada", data.cosecha_estimada_ton ? `${formatNumber(data.cosecha_estimada_ton)} ton` : "--");
    setText("valorCosecha", data.valor_estimado_cosecha_cop ? formatCOP(data.valor_estimado_cosecha_cop) : "--");
    setText("porcentajeCobertura", data.porcentaje_cobertura !== undefined ? `${formatNumber(data.porcentaje_cobertura)}%` : "--");
    setText("valorCobertura", data.valor_cobertura_cop ? formatCOP(data.valor_cobertura_cop) : "--");

    mensaje.classList.remove("error");
    mensaje.textContent = data.mensaje ?? "Consulta realizada correctamente.";
  } catch (error) {
    console.error("Error consultando API:", error);
    mensaje.classList.add("error");
    mensaje.textContent = "No fue posible consultar la API. Revise la conexión o el estado del servicio.";
  } finally {
    btn.disabled = false;
    btn.textContent = "Consultar estimación";
  }
});

cargarMunicipios();
