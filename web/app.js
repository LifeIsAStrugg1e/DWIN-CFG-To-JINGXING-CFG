const state = { file: null, result: null, tab: "mapping" };
const $ = (selector) => document.querySelector(selector);
const fileInput = $("#fileInput");
const dropZone = $("#dropZone");
const convertButton = $("#convertButton");

fileInput.addEventListener("change", () => setFile(fileInput.files[0]));
["dragenter", "dragover"].forEach((event) => dropZone.addEventListener(event, (e) => { e.preventDefault(); dropZone.classList.add("is-dragging"); }));
["dragleave", "drop"].forEach((event) => dropZone.addEventListener(event, (e) => { e.preventDefault(); dropZone.classList.remove("is-dragging"); }));
dropZone.addEventListener("drop", (event) => setFile(event.dataTransfer.files[0]));
convertButton.addEventListener("click", convert);
$("#downloadButton").addEventListener("click", () => {
  if (!state.result) return;
  const blob = new Blob([state.result.text], { type: "text/plain;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "config.TXT";
  link.click();
  URL.revokeObjectURL(link.href);
});
document.querySelectorAll(".tab-button").forEach((button) => button.addEventListener("click", () => selectTab(button.dataset.tab)));

function setFile(file) {
  if (!file) return;
  state.file = file;
  $("#fileName").textContent = file.name;
  $("#fileMeta").textContent = `${formatBytes(file.size)} · 等待转换`;
  convertButton.disabled = false;
  $("#errorBox").hidden = true;
}

async function convert() {
  if (!state.file) return;
  convertButton.disabled = true;
  convertButton.querySelector("span").textContent = "正在读取…";
  $("#errorBox").hidden = true;
  const source = encodeURIComponent($("#sourceModel").value);
  const system = encodeURIComponent($("#targetSystem").value);
  try {
    const response = await fetch(`/api/convert?source_model=${source}&system=${system}`, { method: "POST", body: await state.file.arrayBuffer() });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || "转换失败");
    state.result = payload.result;
    renderResult();
  } catch (error) {
    const box = $("#errorBox");
    box.textContent = error.message;
    box.hidden = false;
  } finally {
    convertButton.disabled = false;
    convertButton.querySelector("span").textContent = "开始转换";
  }
}

function renderResult() {
  const result = state.result;
  $("#emptyState").hidden = true;
  $("#resultContent").hidden = false;
  $("#resultTitle").textContent = `${result.modelName} · ${result.targetSystem}`;
  $("#resultSummary").textContent = `${result.inputSize} 字节 · 文件头 ${result.header}`;
  $("#metricRow").innerHTML = [
    ["源设备", result.modelName], ["目标系统", result.targetSystem], ["字段读取", `${result.sourceFields.length} 项`], ["寄存器输出", `${result.registers.length} 项`],
  ].map(([label, value]) => `<div class="metric"><div class="metric-label">${escapeHtml(label)}</div><div class="metric-value">${escapeHtml(String(value))}</div></div>`).join("");
  renderMapping(result);
  renderRegisters(result);
  renderBytes(result);
  selectTab(state.tab);
}

function renderMapping(result) {
  const fields = result.sourceFields.map((field) => `<div class="field-row"><span class="field-offset">${field.offset}</span><span class="field-name">${escapeHtml(field.label)}</span><span class="field-raw">${escapeHtml(field.raw)}</span><span class="field-value">${escapeHtml(String(field.value))}</span></div>`).join("");
  const mappings = result.mappings.map((row) => `<tr class="${row.active ? "is-active" : "is-inactive"}"><td><div class="path-cell"><span>${escapeHtml(row.source)}</span><span class="path-arrow">→</span><span>${escapeHtml(row.rule)}</span></div></td><td>${escapeHtml(row.sourceValue == null ? "—" : String(row.sourceValue))}</td><td><strong>${escapeHtml(row.target)}</strong> <span class="register-label">${escapeHtml(row.targetLabel)}</span></td><td>${row.bit == null ? "整字节" : `<span class="bit-pill ${row.result === "1" ? "is-one" : ""}">bit ${row.bit}: ${row.result}</span>`}</td><td>${escapeHtml(row.result)}</td></tr>`).join("");
  $("#mappingPanel").innerHTML = `<h3 class="panel-title">源字段</h3><div class="field-list">${fields}</div><h3 class="panel-title mapping-title">目标写入路径</h3><div class="mapping-scroll"><table class="mapping-table"><thead><tr><th>规则</th><th>当前值</th><th>目标</th><th>位</th><th>结果</th></tr></thead><tbody>${mappings}</tbody></table></div>`;
}

function renderRegisters(result) {
  $("#registersPanel").innerHTML = `<div class="register-grid">${result.registers.map((register) => `<div class="register-card"><div class="register-head"><div><span class="register-name">${register.name}</span><span class="register-label"> · ${escapeHtml(register.label)}</span></div><span class="register-value">${register.value}</span></div><div class="bit-row">${register.bits.map((bit, index) => `<span class="bit-cell ${bit === "1" ? "is-one" : ""}" title="bit ${7 - index}">${bit}</span>`).join("")}</div></div>`).join("")}</div>`;
}

function renderBytes(result) {
  $("#bytesPanel").innerHTML = `<div class="byte-table-wrap"><table class="byte-table"><thead><tr><th>偏移</th><th>原始字节</th></tr></thead><tbody>${result.bytes.map((row) => `<tr class="byte-row"><td class="byte-offset">0x${row.offset.toString(16).padStart(4, "0").toUpperCase()}</td><td>${row.hex}</td></tr>`).join("")}</tbody></table></div>`;
}

function selectTab(tab) {
  state.tab = tab;
  document.querySelectorAll(".tab-button").forEach((button) => { const active = button.dataset.tab === tab; button.classList.toggle("is-active", active); button.setAttribute("aria-selected", active); });
  $("#mappingPanel").hidden = tab !== "mapping";
  $("#registersPanel").hidden = tab !== "registers";
  $("#bytesPanel").hidden = tab !== "bytes";
}

function formatBytes(size) { return size < 1024 ? `${size} B` : `${(size / 1024).toFixed(1)} KB`; }
function escapeHtml(value) { return value.replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char])); }
