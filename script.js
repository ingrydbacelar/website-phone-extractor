const btnIniciar = document.getElementById("btnIniciar");
const btnCsv = document.getElementById("btnCsv");
const statusTexto = document.getElementById("statusTexto");
const progressoWrap = document.getElementById("progressoWrap");
const progressoFill = document.getElementById("progressoFill");
const progressoLabel = document.getElementById("progressoLabel");
const tabelaBody = document.getElementById("tabelaBody");
const urlsInput = document.getElementById("urls");

let poller = null;

function renderTabela(results) {
  tabelaBody.innerHTML = "";
  for (const r of results) {
    const tr = document.createElement("tr");
    tr.className = r.status === "ok" ? "status-ok" : "status-erro";
    tr.innerHTML = `
      <td>${r.indice}</td>
      <td>${r.url}</td>
      <td>${r.resultado}</td>
      <td>${r.status}</td>
    `;
    tabelaBody.appendChild(tr);
  }
}

function atualizarProgresso(total, feitos, rodando) {
  if (total === 0) {
    progressoWrap.hidden = true;
    return;
  }
  progressoWrap.hidden = false;
  const pct = Math.round((feitos / total) * 100);
  progressoFill.style.width = pct + "%";
  progressoLabel.textContent = `${feitos} / ${total}`;
  statusTexto.textContent = rodando ? "Extraindo..." : "Concluído.";
}

async function consultarStatus() {
  try {
    const resp = await fetch("/api/status");
    const data = await resp.json();
    renderTabela(data.results);
    atualizarProgresso(data.total, data.results.length, data.running);

    if (!data.running) {
      clearInterval(poller);
      poller = null;
      btnIniciar.disabled = false;
      btnCsv.disabled = data.results.length === 0;
    }
  } catch (e) {
    statusTexto.textContent = "Erro ao consultar status.";
  }
}

btnIniciar.addEventListener("click", async () => {
  const texto = urlsInput.value.trim();
  if (!texto) {
    statusTexto.textContent = "Cole ao menos uma URL.";
    return;
  }

  btnIniciar.disabled = true;
  btnCsv.disabled = true;
  tabelaBody.innerHTML = "";
  statusTexto.textContent = "Iniciando...";

  try {
    const resp = await fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls: texto }),
    });
    const data = await resp.json();

    if (!resp.ok) {
      statusTexto.textContent = data.erro || "Erro ao iniciar.";
      btnIniciar.disabled = false;
      return;
    }

    atualizarProgresso(data.total, 0, true);
    poller = setInterval(consultarStatus, 1000);
  } catch (e) {
    statusTexto.textContent = "Falha ao conectar no servidor.";
    btnIniciar.disabled = false;
  }
});

btnCsv.addEventListener("click", () => {
  window.location.href = "/api/csv";
});
