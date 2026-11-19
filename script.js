const API_URL = "https://hub-ldrs.onrender.com";
const API_TOKEN = ""; // mesma chave definida em API_TOKEN no Render (deixe vazio se não usar)

const btnIniciar = document.getElementById("btnIniciar");
const btnCsv = document.getElementById("btnCsv");
const statusTexto = document.getElementById("statusTexto");
const progressoWrap = document.getElementById("progressoWrap");
const progressoFill = document.getElementById("progressoFill");
const progressoLabel = document.getElementById("progressoLabel");
const tabelaBody = document.getElementById("tabelaBody");
const urlsInput = document.getElementById("urls");

let resultados = [];

function listarUrls() {
  return urlsInput.value.split("\n").map((u) => u.trim()).filter(Boolean);
}

urlsInput.addEventListener("input", () => {
  if (btnIniciar.disabled) return;
  const n = listarUrls().length;
  statusTexto.textContent = n === 0 ? "" : `${n} ${n === 1 ? "site reconhecido" : "sites reconhecidos"}`;
});

function adicionarLinha(r) {
  const tr = document.createElement("tr");
  tr.className = r.status === "ok" ? "status-ok" : "status-erro";
  [r.indice, r.url, r.resultado, r.status].forEach((v) => {
    const td = document.createElement("td");
    td.textContent = v;
    tr.appendChild(td);
  });
  tabelaBody.appendChild(tr);
}

function atualizarProgresso(total, feitos) {
  progressoWrap.hidden = false;
  progressoFill.style.width = Math.round((feitos / total) * 100) + "%";
  progressoLabel.textContent = `${feitos} / ${total}`;
}

async function extrair(url) {
  const headers = { "Content-Type": "application/json" };
  if (API_TOKEN) headers["X-Token"] = API_TOKEN;
  try {
    const resp = await fetch(API_URL + "/extrair", {
      method: "POST",
      headers,
      body: JSON.stringify({ url }),
    });
    const data = await resp.json();
    if (!resp.ok) return { resultado: data.detail || `HTTP ${resp.status}`, status: "erro" };
    if (data.telefone) return { resultado: data.telefone, status: "ok" };
    return { resultado: data.erro || "Nenhum telefone encontrado", status: "erro" };
  } catch (e) {
    return { resultado: "Falha ao conectar na API", status: "erro" };
  }
}

btnIniciar.addEventListener("click", async () => {
  const urls = listarUrls();
  if (urls.length === 0) {
    statusTexto.textContent = "Cole ao menos uma URL.";
    return;
  }

  btnIniciar.disabled = true;
  btnCsv.disabled = true;
  tabelaBody.innerHTML = "";
  resultados = [];
  statusTexto.textContent = "Extraindo...";
  atualizarProgresso(urls.length, 0);

  for (let i = 0; i < urls.length; i++) {
    const r = { indice: i + 1, url: urls[i], ...(await extrair(urls[i])) };
    resultados.push(r);
    adicionarLinha(r);
    atualizarProgresso(urls.length, i + 1);
  }

  statusTexto.textContent = "Concluído.";
  btnIniciar.disabled = false;
  btnCsv.disabled = false;
});

btnCsv.addEventListener("click", () => {
  const esc = (v) => `"${String(v).replace(/"/g, '""')}"`;
  const linhas = [["#", "URL", "Resultado", "Status"].map(esc).join(";")];
  for (const r of resultados) {
    linhas.push([r.indice, r.url, r.resultado, r.status].map(esc).join(";"));
  }
  const blob = new Blob(["\ufeff" + linhas.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "telefones.csv";
  a.click();
  URL.revokeObjectURL(a.href);
});
