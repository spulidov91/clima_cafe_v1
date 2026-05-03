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

function formatPercent(value) {
  if (value === null || value === undefined || isNaN(Number(value))) {
    return "--";
  }

  const numericValue = Number(value);
  const percentValue = numericValue <= 1 ? numericValue * 100 : numericValue;

  return `${formatNumber(percentValue)}%`;
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

function mostrarMensaje(texto, esError = false) {
  const mensaje = document.getElementById("mensajeResultado");

  mensaje.classList.toggle("error", esError);
  mensaje.textContent = texto;
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
    mostrarMensaje("No fue posible cargar la lista de municipios. Revise el estado de la API.", true);
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

  btn.disabled = true;
  btn.textContent = "Calculando resultado...";
  mostrarMensaje("Estamos calculando la estimación con la información climática y satelital disponible.");

  const payload = {
    numero_identidad: document.getElementById("numero_identidad").value.trim(),
    municipio: document.getElementById("municipio").value.trim(),
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
      setText("tipoRespuesta", "No procesada");
      mostrarMensaje(
        data.detail
          ? `No fue posible procesar la consulta: ${JSON.stringify(data.detail)}`
          : "No fue posible procesar la consulta. Revise los datos ingresados.",
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

    setText("trm", data.trm_cop_usd ? formatCOP(data.trm_cop_usd) : "--");
    setText("precioInternacional", data.precio_internacional_usd_lb ? formatUSD(data.precio_internacional_usd_lb) : "--");
    setText("precioLocal", precioLocalLb ? `${formatCOP(precioLocalLb)} / lb` : "--");

    setText("tipoRespuesta", response.ok ? "Consulta exitosa" : "No procesada");
    setText("cosechaEstimada", data.cosecha_estimada_ton ? `${formatNumber(data.cosecha_estimada_ton)} ton` : "--");
    setText("valorCosecha", data.valor_estimado_cosecha_cop ? formatCOP(data.valor_estimado_cosecha_cop) : "--");
    setText("porcentajeCobertura", data.porcentaje_cobertura !== undefined ? formatPercent(data.porcentaje_cobertura) : "--");
    setText("valorCobertura", data.valor_cobertura_cop ? formatCOP(data.valor_cobertura_cop) : "--");

    mostrarMensaje(
      data.mensaje ??
      "Consulta realizada correctamente. Los resultados muestran la producción estimada y el valor aproximado de cobertura para el cultivo."
    );

  } catch (error) {
    console.error("Error consultando API:", error);
    setText("tipoRespuesta", "Error de conexión");
    mostrarMensaje(
      "No fue posible consultar la API. Revise la conexión o el estado del servicio.",
      true
    );
  } finally {
    btn.disabled = false;
    btn.textContent = "Estimar mi cosecha";
  }
});

cargarMunicipios();
