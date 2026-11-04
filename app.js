"use strict";
const app = document.getElementById("app");
const S = { user: null, id: null, det: null, timer: null };

function h(tag, props, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const k of kids.flat(Infinity)) { if (k == null || k === false) continue; e.append(k.nodeType ? k : document.createTextNode(String(k))); }
  return e;
}
async function api(method, url, body, extra) {
  const r = await fetch(url, { method, credentials: "same-origin",
    headers: Object.assign({ "X-Requested-With": "alex" }, body && !(body instanceof Blob) ? { "Content-Type": "application/json" } : {}, extra || {}),
    body: body instanceof Blob ? body : body ? JSON.stringify(body) : undefined });
  let d = {}; try { d = await r.json(); } catch (e) {}
  if (r.status === 401 && url !== "/api/login") { S.user = null; vistaLogin(); throw new Error("sesión"); }
  if (!r.ok) throw new Error(d.error || "Error " + r.status);
  return d;
}
function pintar(...n) { app.replaceChildren(...n); window.scrollTo(0, 0); }
function marco(...contenido) {
  return [h("header", {}, h("b", {}, "A-LEX MAGISTER"), h("span", {}, S.user || "",
    h("button", { onclick: async () => { await api("POST", "/api/logout"); S.user = null; vistaLogin(); } }, "Salir"))), h("main", {}, ...contenido)];
}
const LEYENDA = h("div", { class: "aviso" }, "Las propuestas de A-LEX MAGISTER son apoyo técnico y no constituyen determinación jurídica. La decisión final corresponde al usuario.");

function vistaLogin(msg) {
  const e = h("input", { type: "email", autocomplete: "username", placeholder: "Correo" });
  const p = h("input", { type: "password", autocomplete: "current-password", placeholder: "Contraseña" });
  const er = h("div", { class: "err" }, msg || "");
  const entrar = async () => { try { const d = await api("POST", "/api/login", { email: e.value, password: p.value }); S.user = d.email; vistaLista(); } catch (x) { er.textContent = x.message; } };
  p.addEventListener("keydown", (ev) => { if (ev.key === "Enter") entrar(); });
  pintar(h("div", { class: "login card" }, h("h1", {}, "A-LEX MAGISTER"), h("div", { class: "sub" }, "Acceso para usuarios autorizados"), h("br"), e, p, er, h("button", { onclick: entrar }, "Entrar")));
}

function zona(textoGrande, alSoltar) {
  const inp = h("input", { type: "file", multiple: true, accept: ".pdf,.docx,.txt", class: "oculto" });
  const z = h("div", { class: "drop", tabindex: "0" }, h("big", {}, textoGrande), "Arrastre archivos Word, PDF o TXT, o haga clic para elegirlos", inp);
  const fin = (fs) => { if (fs && fs.length) alSoltar(Array.from(fs)); };
  z.addEventListener("click", () => inp.click());
  inp.addEventListener("change", () => fin(inp.files));
  z.addEventListener("dragover", (ev) => { ev.preventDefault(); z.classList.add("on"); });
  z.addEventListener("dragleave", () => z.classList.remove("on"));
  z.addEventListener("drop", (ev) => { ev.preventDefault(); z.classList.remove("on"); fin(ev.dataTransfer.files); });
  return z;
}
async function subir(id, archivos, estado) {
  const errores = [];
  for (const [i, f] of archivos.entries()) {
    estado.textContent = `Subiendo ${i + 1} de ${archivos.length}: ${f.name}`;
    try { await api("POST", `/api/expedientes/${id}/documentos`, f, { "X-Filename": encodeURIComponent(f.name) }); } catch (x) { errores.push(`${f.name}: ${x.message}`); }
  }
  estado.textContent = errores.join(" · ");
}

async function vistaLista() {
  clearInterval(S.timer); S.id = null;
  const estado = h("div", { class: "err" });
  const lista = await api("GET", "/api/expedientes");
  pintar(...marco(h("h1", {}, "Sus expedientes"),
    zona("Arrastre aquí los documentos del expediente", async (fs) => {
      const n = await api("POST", "/api/expedientes"); await subir(n.id, fs, estado); vistaExp(n.id); }),
    estado,
    h("p", {}, h("button", { class: "sec", onclick: async () => { const n = await api("POST", "/api/expedientes/demo"); vistaExp(n.id); } }, "Probar con un expediente de ejemplo (datos sintéticos)")),
    lista.length ? h("h2", {}, "Anteriores") : null,
    lista.map((x) => h("div", { class: "card fila" }, h("div", {}, h("b", {}, x.nombre), h("div", { class: "sub" }, x.creado)),
      h("div", {}, h("span", { class: "badge" }, x.estado), " ", h("button", { class: "sec", onclick: () => vistaExp(x.id) }, "Abrir"))))));
}

async function vistaExp(id) {
  clearInterval(S.timer); S.id = id;
  const d = await api("GET", `/api/expedientes/${id}`); S.det = d; dibujar(d);
  if (d.estado === "procesando") S.timer = setInterval(async () => {
    try { const n = await api("GET", `/api/expedientes/${id}`); if (n.estado !== "procesando") { clearInterval(S.timer); S.det = n; dibujar(n); } } catch (e) { clearInterval(S.timer); } }, 2000);
}

const etiqueta = (e) => ({ propuesto: ["Por revisar", "b-ale"], confirmado_por_usuario: ["Extracción confirmada", "b-ok"], confirmado: ["Confirmado", "b-ok"], rechazado: ["Rechazado", "b-mal"] }[e] || [e, ""]);
function badge(e) { const [t, c] = etiqueta(e); return h("span", { class: "badge " + c }, t); }
function citaDe(f) { return h("div", { class: "cita" }, `“${f.fragmento}”`, h("div", {}, `${f.documento} · ${f.ubicacion}`)); }

function dibujar(d) {
  const id = d.id, mapH = Object.fromEntries(d.hechos.map((x) => [x.id, x])), mapP = Object.fromEntries(d.pruebas.map((x) => [x.id, x]));
  const decidir = async (tipo, ident, accion) => { S.det = await api("POST", `/api/expedientes/${id}/decision`, { tipo, id: ident, accion }); dibujar(S.det); };
  const botones = (tipo, ident, est) => est === "propuesto" ? h("div", { class: "btns" },
    h("button", { onclick: () => decidir(tipo, ident, "confirmar") }, tipo === "vinculo" ? "Confirmar relación" : "Confirmar extracción"),
    h("button", { class: "mal", onclick: () => decidir(tipo, ident, "rechazar") }, "Rechazar")) : null;
  const nombreH = (x) => `${x.evento} · ${x.atributo}: ${x.valor}`;

  const estadoSub = h("div", { class: "err" });
  const env = d.envio;
  let accion;
  if (d.estado === "procesando") accion = h("div", { class: "card" }, h("b", {}, "Analizando…"), h("div", { class: "sub" }, "Esto puede tardar un minuto. Puede dejar esta página abierta."));
  else if (!env.disponible) accion = h("div", { class: "aviso" }, env.motivo);
  else {
    const chk = h("input", { type: "checkbox", id: "aut", class: "chk" });
    const btn = h("button", { onclick: async () => { try { await api("POST", `/api/expedientes/${id}/analizar`, { consentimiento: env.consentimiento_vigente || chk.checked }); vistaExp(id); } catch (x) { estadoSub.textContent = x.message; } } },
      d.estado === "listo" ? "Volver a analizar" : "Analizar documentos");
    if (!env.consentimiento_vigente) btn.disabled = true;
    chk.addEventListener("change", () => { btn.disabled = !chk.checked; });
    accion = h("div", { class: "card" },
      env.externo ? h("p", {}, "Para analizar, el contenido de estos documentos se enviará a ", h("b", {}, env.proveedor), " (modelo ", h("b", {}, env.modelo), ").")
                  : h("p", {}, "Modo demostración: con datos sintéticos. Nada sale de este servidor."),
      env.consentimiento_vigente ? h("p", { class: "sub" }, "Envío ya autorizado para esta configuración.") : h("label", {}, chk, "Autorizo este envío"),
      h("div", {}, btn), estadoSub);
  }
  const est = h("div", { class: "err" });
  const agregar = d.estado === "procesando" ? null : zona("Agregar más documentos", async (fs) => { await subir(id, fs, est); vistaExp(id); });

  const resumen = [];
  if (d.estado === "listo") {
    resumen.push(h("h2", {}, "Resumen"), LEYENDA);
    const sinP = Object.entries(d.cobertura.hechos).filter(([, v]) => v[0] === "SIN_PRUEBA").map(([k]) => mapH[k]);
    const sinH = Object.entries(d.cobertura.pruebas).filter(([, v]) => v[0] === "SIN_HECHO").map(([k]) => mapP[k]);
    resumen.push(h("div", { class: "card" }, h("b", {}, `${d.pendientes} propuestas por revisar`), " · ", `${d.contradicciones.length} contradicciones · ${sinP.length} hechos sin prueba · ${sinH.length} pruebas sin hecho`));
    if (d.errores_verificacion.length) resumen.push(h("div", { class: "aviso" }, "El verificador marcó elementos con sustento insuficiente: ", JSON.stringify(d.errores_verificacion)));
    for (const c of d.contradicciones) resumen.push(h("div", { class: "card contra" }, h("b", {}, `Contradicción documental: ${c.evento} · ${c.atributo}`),
      h("div", { class: "dos" }, c.versiones.map((v) => h("div", {}, h("div", {}, h("b", {}, v.valor), ` — afirma: ${v.afirma} `, badge(v.estado === "declarado" ? "propuesto" : v.estado)), h("div", { class: "cita" }, `“${v.fragmento}”`, h("div", {}, `${v.documento} · ${v.ubicacion}`))))),
      h("div", { class: "sub" }, "Pendiente: la resolución corresponde a usted. El sistema no decide cuál versión es la correcta.")));
    if (sinP.length) resumen.push(h("div", { class: "card" }, h("b", {}, "Hechos sin correlación de prueba: analizar su pertinencia"), h("ul", {}, sinP.map((x) => h("li", {}, nombreH(x))))));
    if (sinH.length) resumen.push(h("div", { class: "card" }, h("b", {}, "Pruebas sin hecho vinculado: analizar su pertinencia"), h("ul", {}, sinH.map((x) => h("li", {}, `${x.tipo}: ${x.descripcion}`)))));
    if (d.rechazados_verificador.length) resumen.push(h("details", {}, h("summary", {}, `${d.rechazados_verificador.length} propuestas de la IA descartadas por el verificador (cita no verificable)`),
      h("ul", {}, d.rechazados_verificador.map((r) => h("li", { class: "sub" }, `${r[0]}: ${r[2]}`)))));
  }
  const act = (arr) => arr.filter((x) => x.estado !== "rechazado"), rech = (arr) => arr.filter((x) => x.estado === "rechazado");
  const bloqueH = d.hechos.length ? [h("h2", {}, "Hechos"), act(d.hechos).map((x) => h("div", { class: "card" }, h("div", { class: "fila" }, h("b", {}, nombreH(x)), badge(x.estado)),
      h("div", { class: "sub" }, `Lo afirma: ${x.afirma}`), citaDe(x.fuente), botones("hecho", x.id, x.estado))),
      rech(d.hechos).length ? h("details", {}, h("summary", {}, `Rechazados (${rech(d.hechos).length})`), rech(d.hechos).map((x) => h("div", { class: "card sub" }, nombreH(x)))) : null] : [];
  const bloqueP = d.pruebas.length ? [h("h2", {}, "Pruebas"), act(d.pruebas).map((x) => h("div", { class: "card" }, h("div", { class: "fila" }, h("b", {}, x.descripcion), badge(x.estado)),
      h("div", { class: "sub" }, `Tipo: ${x.tipo}`), citaDe(x.fuente), botones("prueba", x.id, x.estado))),
      rech(d.pruebas).length ? h("details", {}, h("summary", {}, `Rechazadas (${rech(d.pruebas).length})`), rech(d.pruebas).map((x) => h("div", { class: "card sub" }, x.descripcion))) : null] : [];
  const vs = d.vinculos.filter((v) => v.estado !== "rechazado" && mapH[v.hecho_id] && mapP[v.prueba_id]);
  const bloqueV = vs.length ? [h("h2", {}, "Relaciones hecho ↔ prueba"), vs.map((v) => h("div", { class: "card" }, h("div", { class: "fila" }, h("b", {}, nombreH(mapH[v.hecho_id])), badge(v.estado === "declarado" ? "propuesto" : v.estado)),
      h("div", {}, `↔ ${mapP[v.prueba_id].descripcion} (${mapP[v.prueba_id].tipo})`), h("div", { class: "sub" }, v.explicacion), botones("vinculo", `${v.hecho_id}|${v.prueba_id}`, v.estado)))] : [];

  pintar(...marco(h("a", { class: "volver", onclick: vistaLista }, "← Expedientes"), h("h1", {}, d.nombre),
    d.error ? h("div", { class: "err" }, d.error) : null,
    h("h2", {}, `Documentos (${d.documentos.length})`),
    d.documentos.map((x) => h("div", { class: "card" }, h("b", {}, x.nombre), h("div", { class: "sub" }, "SHA-256: " + x.sha256.slice(0, 16) + "…"), x.avisos.map((a) => h("div", { class: "err" }, a)))),
    agregar, est, h("h2", {}, "Análisis"), accion, resumen, bloqueH, bloqueP, bloqueV));
}

(async () => { try { const y = await api("GET", "/api/yo"); S.user = y.email; vistaLista(); } catch (e) { vistaLogin(); } })();
