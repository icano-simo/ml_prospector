/*
 * Volcado del DOM de Model Match a JSON.
 *
 * Es la SEGUNDA opcion, despues del export nativo. Se usa cuando el boton
 * "Export Profile" no da lo que hace falta.
 *
 * Como se usa
 * -----------
 *   1. Abri el perfil o la pestaña Market Signals en el navegador.
 *   2. F12 -> Console.
 *   3. Pega este archivo completo y Enter.
 *   4. Se descarga un .json con el nombre correcto.
 *
 * Que hace y que NO hace
 * ----------------------
 * Vuelca el texto de las tablas y tarjetas visibles, con la pestaña activa y un
 * timestamp. NO interpreta, NO normaliza y NO elige entre valores en conflicto:
 * eso lo hace parser.py, que necesita ver el conflicto para reportarlo.
 *
 * Los selectores de Model Match van a cambiar. Por eso el volcado es
 * deliberadamente tonto: agarra toda tabla y todo elemento con numeros, en vez
 * de apuntar a clases especificas que se rompen con cada deploy. Si queda
 * ruido, el ruido se filtra despues; lo que no se puede recuperar despues es un
 * dato que el selector no agarro.
 */
(function () {
  "use strict";

  var ESQUEMA = "mm-captura-v1";

  function texto(el) {
    return (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
  }

  function volcarTablas() {
    return Array.prototype.map.call(document.querySelectorAll("table"), function (tabla, i) {
      var filas = Array.prototype.map.call(tabla.querySelectorAll("tr"), function (tr) {
        return Array.prototype.map.call(tr.querySelectorAll("th,td"), texto);
      }).filter(function (f) { return f.length > 0; });
      return { indice: i, filas: filas };
    }).filter(function (t) { return t.filas.length > 1; });
  }

  /* Tarjetas y KPIs: cualquier elemento chico cuyo texto tenga un numero.
     El umbral de 200 caracteres evita arrastrar contenedores enteros. */
  function volcarTarjetas() {
    var vistos = Object.create(null);
    var salida = [];
    var candidatos = document.querySelectorAll(
      "div,span,p,li,dd,dt,h1,h2,h3,h4,h5,h6"
    );
    for (var i = 0; i < candidatos.length; i++) {
      var el = candidatos[i];
      if (el.children.length > 3) continue;
      var t = texto(el);
      if (!t || t.length > 200) continue;
      if (!/[0-9]/.test(t)) continue;
      if (vistos[t]) continue;
      vistos[t] = true;
      salida.push(t);
    }
    return salida;
  }

  /* Los tooltips suelen traer el dato que la tarjeta esconde, por ejemplo
     "Total Volume $1.0M · Mortgaged Volume: $0", que es como se descubrio que
     la tasa de casamiento hipotecario es baja. */
  function volcarTitulosYAria() {
    var salida = [];
    var els = document.querySelectorAll("[title],[aria-label],[data-tooltip]");
    for (var i = 0; i < els.length; i++) {
      var v = els[i].getAttribute("title")
        || els[i].getAttribute("aria-label")
        || els[i].getAttribute("data-tooltip");
      if (v && v.trim() && salida.indexOf(v.trim()) === -1) {
        salida.push(v.trim());
      }
    }
    return salida;
  }

  function pestanaActiva() {
    var sel = '[role="tab"][aria-selected="true"], .active[role="tab"], '
      + 'nav a[aria-current], .tab.active, li.active a';
    var el = document.querySelector(sel);
    return el ? texto(el) : "[no detectada]";
  }

  var volcado = {
    esquema: ESQUEMA,
    capturado_en: new Date().toISOString(),
    url: location.href,
    titulo: document.title,
    pestana_activa: pestanaActiva(),
    // Todo texto visible que mencione una ventana de tiempo. El grano es la
    // primera cosa que hay que verificar en cualquier export.
    ventanas_mencionadas: volcarTarjetas().filter(function (t) {
      return /\b(month|months|trailing|TTM|20\d\d|last \d+)\b/i.test(t);
    }),
    tablas: volcarTablas(),
    tarjetas: volcarTarjetas(),
    tooltips: volcarTitulosYAria(),
  };

  var json = JSON.stringify(volcado, null, 2);

  var slug = (document.title || "modelmatch")
    .replace(/[^A-Za-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 60);
  var fecha = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  var nombre = "mm_" + slug + "_" + fecha + ".json";

  var blob = new Blob([json], { type: "application/json" });
  var a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = nombre;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);

  console.log(
    "Volcado: " + nombre
    + "\n  pestaña: " + volcado.pestana_activa
    + "\n  tablas: " + volcado.tablas.length
    + "  tarjetas: " + volcado.tarjetas.length
    + "  tooltips: " + volcado.tooltips.length
    + "\n  ventanas mencionadas: " + JSON.stringify(volcado.ventanas_mencionadas)
    + "\n\nVerifica el grano antes de usar estos numeros: suma cada seccion y"
    + "\ncompara los totales. Si una seccion suma 29 y otra dice 728, hay dos"
    + "\nuniversos distintos en un solo volcado."
  );

  return nombre;
})();
