/* La plantilla de la ficha v3: JSON -> el HTML de la maqueta.
 *
 * Cómo se ve lo decide `ficha_v3.css`, que salió de la maqueta tal cual. Qué
 * dice lo decide el JSON. Quedan separados a propósito: así «igual a la
 * maqueta» es algo que se puede medir --renderizar el golden y compararlo--
 * en vez de algo que se opina.
 *
 * Los campos `escribe: codigo` los llena la app desde la base. Los `escribe:
 * ia` salen de la ficha redactada, y **solo si pasaron el validador**: una
 * sección que no pasa se pinta como «Pendiente: no pasó la validación» y las
 * de código se pintan igual. Nunca se muestra un texto sin validar, y nunca se
 * pierde lo que sí está comprobado.
 */
(function (global) {
  'use strict';

  function esc(s) {
    return legible(String(s == null ? '' : s))
      .replace(/[&<>"']/g, function (c) {
        return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;',
                "'": '&#39;'}[c];
      });
  }

  /* Las fechas ISO y los teléfonos E.164 que vienen DENTRO de un texto.
   *
   * El motivo del veredicto se escribió cuando se evaluó al realtor y se
   * guardó tal cual: «hay que volver a capturar Transactions después del
   * 2026-10-19». Arreglar el motor arregla los veredictos que se escriban de
   * hoy en adelante, no los cuatro mil que ya están guardados, y volver a
   * evaluar producción para cambiar el formato de una fecha no es algo que se
   * haga.
   *
   * Así que se traduce al mostrarlo. Va dentro de `esc` a propósito: es el
   * único sitio por el que pasa TODO texto, y una lista de campos a los que
   * acordarse de aplicárselo se desactualiza sola. Lo exporta `fichaV3Utils`
   * porque las otras pestañas de la app tienen el mismo problema y una segunda
   * implementación acabaría diciendo otra cosa.
   *
   * Tres casos, en orden, y el orden importa:
   *   · `2026-09-23T14:05` -> `23 sep 2026 14:05`, con la hora intacta;
   *   · `2026-10-19` suelta -> `19 oct 2026`;
   *   · `+17733625798` -> `(773) 362-5798`.
   *
   * Lo que NO se toca: `2026-09-24-v2`, que es el nombre de la versión del
   * prompt y no una fecha. De ahí los `(?<![\d-])` / `(?![\d:T-])`. */
  function legible(s) {
    if (!s) return s;
    return String(s)
      .replace(/(?<![\d-])(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?/g,
        function (_, d, h) { return fecha(d) + ' ' + h; })
      .replace(/(?<![\d-])\d{4}-\d{2}-\d{2}(?![\d:T-])/g,
        function (t) { return fecha(t); })
      .replace(/(?<!\d)\+1(\d{3})(\d{3})(\d{4})(?!\d)/g, '($1) $2-$3');
  }

  /* `2026-03-11` se muestra como 11 mar 2026, no como 10.
   *
   * `new Date('2026-03-11')` se parsea como MEDIANOCHE UTC, y al formatearla
   * en hora local --Colombia es UTC-5-- sale el día anterior. Toda la ficha
   * está llena de fechas de closings y de posts, así que el error no era una:
   * eran todas, siempre un día antes, y siempre plausible. */
  /* Los meses, escritos y no pedidos al navegador.
     `toLocaleDateString('es', {month:'short'})` devuelve «sept» en Chrome, y
     `motor/fechas.py` escribe «sep»: la misma fecha salía distinta según
     quién la hubiera formateado, en la misma pantalla. La tabla es la de
     `motor/fechas.py`. */
  var MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
               'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

  function fecha(iso) {
    if (!iso) return '';
    var s = String(iso);
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
    var d = m ? new Date(+m[1], +m[2] - 1, +m[3]) : new Date(s);
    if (isNaN(d)) return s.slice(0, 10);
    return d.getDate() + ' ' + MESES[d.getMonth()] + ' ' + d.getFullYear();
  }

  /* `$5,3M` sin espacio y sin poder partirse. Con un espacio normal el KPI
   * se cortaba en dos líneas --«$5,3» arriba y «M» abajo-- y un número
   * partido a la mitad se lee mal antes de leerse bien. */
  function dinero(n) {
    if (n == null) return '—';
    if (n >= 1e6) return '$' + (n / 1e6).toFixed(1).replace('.', ',') + 'M';
    if (n >= 1e3) return '$' + Math.round(n / 1e3) + 'K';
    return '$' + n;
  }

  /* Un teléfono se muestra como se marca, no como se guarda. `+17733625798`
   * es el formato de comparación; el BD lee `(773) 362-5798`. */
  function telefono(v) {
    var s = String(v == null ? '' : v);
    var m = /^\+1(\d{3})(\d{3})(\d{4})$/.exec(s.replace(/\s/g, ''));
    return m ? '(' + m[1] + ') ' + m[2] + '-' + m[3] : s;
  }

  /* «Pendiente» SIEMPRE con su motivo. Sin motivo es un hueco con otro nombre:
     nadie sabe qué hay que hacer para resolverlo. */
  function pendiente(motivo) {
    return '<span class="pendiente">Pendiente</span> ' + esc(motivo || '');
  }

  /* El bloque plegado con la evidencia. Es la regla número uno de la ficha:
     cada dato lleva de dónde sale, con la cita y su fecha. */
  function deDondeSale(items) {
    var ds = (items || []).filter(Boolean);
    if (!ds.length) return '';
    return '<details class="src"><summary>De dónde sale</summary>' +
      '<div class="evid">' + ds.map(function (d) {
        if (typeof d === 'string') return '<div>' + esc(d) + '</div>';
        return '<div>' +
          (d.texto_literal ? '<q>' + esc(d.texto_literal) + '</q>' : '') +
          '<span class="d">' +
          (d.fecha ? esc(fecha(d.fecha)) + (d.nota ? '. ' : '') : '') +
          esc(d.nota || '') + '</span></div>';
      }).join('') + '</div></details>';
  }

  /* Una sección que no pasó el validador. Se dice QUÉ pasó, no se oculta. */
  function noValido(motivos) {
    return '<p class="muestra">' + pendiente(
      'no pasó la validación (' + (motivos || []).join('; ') + ')') + '</p>';
  }

  function ok(d, seccion) {
    var m = (d._no_validas || {})[seccion];
    return m ? null : true;
  }

  /* El texto largo de un pendiente, por su `item`. Lo escribe el código, así
     que la sección que lo muestra no tiene que repetirlo -- y cuando cambie
     («con licencia en Illinois»), cambia en un solo sitio. */
  function _pendienteDe(d, item) {
    var p = (d.pendientes || []).find(function (x) {
      return x && x.item === item;
    });
    return p ? (p.texto_visible || p.motivo || '') : '';
  }

  /* ── 1 · Quién es ─────────────────────────────────────────────────────── */
  function quienEs(d) {
    var c = d.cabecera || {};
    var contactos = {};
    (c.contactos || []).forEach(function (x) {
      (contactos[x.canal] = contactos[x.canal] || []).push(x);
    });
    /* `direccion` decía «Oficina», igual que `oficina`, así que la ficha
       mostraba dos filas con la misma etiqueta y distinto contenido. */
    var ETIQUETA = {telefono: 'Teléfono', email: 'Email', oficina: 'Oficina',
                    direccion: 'Dirección', instagram: 'Instagram',
                    web: 'Web', otro: 'Otro'};
    var filas = Object.keys(contactos).map(function (k) {
      return '<div class="fila"><span class="k">' + esc(ETIQUETA[k] || k) +
        '</span><span class="v">' + contactos[k].map(function (x) {
          /* `difiere` significa que el dato está en UNA sola fuente y no
             coincide con el resto. Se dice, no se marca solo con un color: un
             color sin texto obliga a adivinar qué quiere decir. */
          return '<span class="dato"><span class="val">' +
            esc(x.canal === 'telefono' ? telefono(x.valor) : x.valor) +
            '</span>' + (x.fuentes || []).map(function (f) {
              return '<span class="fuente' + (x.difiere ? ' dif' : '') + '">' +
                esc(x.difiere ? 'Solo en ' + f.charAt(0).toLowerCase() +
                    f.slice(1) : f) + '</span>';
            }).join('') + '</span>';
        }).join('') + '</span></div>';
    }).join('');

    return '<section class="ficha" aria-label="Quién es"><div>' +
      '<div class="quien-es"><div class="avatar" aria-hidden="true">' +
      esc(c.iniciales || '··') + '</div><div><h1>' + esc(c.nombre || '—') +
      '</h1><p class="meta">' + esc(c.meta || '') + '</p></div></div>' +
      (ok(d, 'cabecera')
        ? '<p class="bio">' + esc((c.bio || {}).texto || '') + '</p>' +
          deDondeSale(c.bio_evidencias_visibles)
        : '<p class="bio">' + noValido((d._no_validas || {}).cabecera) + '</p>') +
      '</div><div class="contacto" aria-label="Contacto">' +
      (filas || '<div class="fila"><span class="k">Contacto</span>' +
        '<span class="v">' + pendiente('no hay datos suyos en la base') +
        '</span></div>') + '</div></section>';
  }

  /* ── 2 · Veredicto + Salesforce ───────────────────────────────────────── */
  function veredicto(d) {
    var v = d.veredicto || {}, sf = d.salesforce || {};
    var SELLO = {ok: '✓ Se le puede escribir',
                 excluido: '✕ No se le escribe',
                 pendiente_modelmatch: '▲ Falta Model Match'};
    var sfCuerpo;
    if (sf.pendiente) {
      sfCuerpo = '<p class="muestra">' + pendiente(sf.pendiente) + '</p>';
    } else {
      sfCuerpo = '<dl class="sf-grid">' +
        [['Lead', (sf.lead || '') + (sf.status ? ' · <b>' + esc(sf.status) +
           '</b>' : '')],
         ['Owner', esc(sf.owner || '')],
         ['Lead Source', esc(sf.lead_source || '')],
         ['Creado', esc(fecha(sf.creado))],
         ['Actividad', esc(sf.actividad || '')]]
        .filter(function (p) { return p[1]; })
        .map(function (p) {
          return '<dt>' + p[0] + '</dt><dd>' + p[1] + '</dd>';
        }).join('') + '</dl>';
    }
    return '<section class="veredicto" aria-label="Veredicto">' +
      '<span class="sello">' + esc(SELLO[v.estado] || '▲ Sin veredicto') +
      '</span><p class="porque">' + esc(v.texto || v.motivo || '') + '</p>' +
      '<div class="sf"><b>Salesforce</b>' + sfCuerpo +
      deDondeSale(sf.de_donde_sale ? [sf.de_donde_sale] : []) +
      '</div></section>';
  }

  /* ── 3 · Por qué ella ─────────────────────────────────────────────────── */
  function porQueElla(d) {
    var p = d.por_que_ella || {};
    var cuerpo = ok(d, 'por_que_ella')
      ? '<ol class="razones">' + (p.razones || []).map(function (r) {
          /* `de_donde_sale` puede traer prosa, citas o las dos. La prosa va
             primero: es lo que el BD lee de un vistazo. */
          var dd = r.de_donde_sale || r.de_donde;
          var items = [];
          if (dd && typeof dd === 'string') items.push(dd);
          else if (dd) {
            if (dd.texto) items.push(dd.texto);
            (dd.citas || []).forEach(function (c) { items.push(c); });
          }
          return '<li><h3>' + esc(r.titulo) + '</h3><p>' + esc(r.texto) +
            '</p>' + deDondeSale(items) + '</li>';
        }).join('') + '</ol>'
      : noValido((d._no_validas || {}).por_que_ella);
    var razonesEncaje = (d.encaje && ok(d, 'encaje')
                         && (d.encaje.razones || []).length)
      ? '<ul class="lista" style="margin-top:10px">' +
        d.encaje.razones.map(function (r) {
          return '<li>' + esc(r.texto) + '</li>';
        }).join('') + '</ul>'
      : '';
    cuerpo += razonesEncaje;
    /* La prioridad la escribe el CÓDIGO y se pinta tal cual: poner aquí un
       valor por defecto en mayúscula fue lo que hizo que la plantilla dijera
       «Prioridad: Pendiente» donde la maqueta dice «pendiente». */
    /* El texto sale del pendiente «puntaje», que es donde el código lo
       escribe entero («Prioridad: pendiente»). Componerlo aquí a partir de un
       valor suelto fue lo que dejó «Prioridad: Pendiente» con mayúscula. */
    var prio = _pendienteDe(d, 'puntaje');
    if (!prio) {
      var v = p.prioridad;
      if (v && typeof v === 'object') v = v.pendiente;
      prio = 'Prioridad: ' + (v || 'pendiente');
    }
    return '<section class="porque-ella" aria-label="Por qué ella">' +
      '<div class="prioridad"><h2 style="font-size:21px">Por qué ella</h2>' +
      '<span class="pendiente">' + esc(prio) + '</span>' + encaje(d) +
      '</div>' + cuerpo + '</section>';
  }

  /* El encaje con nuestro cliente. Va JUNTO a «Por qué ella» y no como
   * sección aparte: las razones para hablarle y si nos encaja se leen juntas o
   * no se leen.
   *
   * Es juicio de la IA y por eso lleva su grado visible: «Cliente ideal» sin
   * la marca se lee como un dato, y no lo es. */
  function encaje(d) {
    var e = d.encaje;
    if (!e || !e.clase || !ok(d, 'encaje')) return '';
    var CLASE = {'Cliente ideal': 'ok', 'Revisar': 'warn',
                 'Nutrición': 'ask'};
    var color = CLASE[e.clase] || 'warn';
    return '<span class="grado ' +
      (color === 'ok' ? 'dato' : color === 'ask' ? 'ella' : 'hip') +
      '" title="' + esc((e.razones || []).map(function (r) {
        return r.texto;
      }).join(' · ')) + '">' + esc(e.clase) + ' · Hipótesis</span>';
  }

  /* ── 4 · Dolores posibles ─────────────────────────────────────────────── */
  function dolores(d) {
    var CLASE = {'Dato': 'dato', 'Lo cuenta ella': 'ella',
                 'Hipótesis': 'hip', 'Hipótesis el porqué': 'hip'};
    var cuerpo = ok(d, 'dolores')
      ? '<div class="dolores-wrap"><table class="dolores"><thead><tr>' +
        '<th>Dolor posible</th><th>Evidencia</th><th>Grado</th>' +
        '<th>Pregunta para validarlo</th></tr></thead><tbody>' +
        /* `data-col` es el nombre de la columna pegado a la celda. En un panel
         * angosto la tabla se apila --cada fila es un bloque-- y el encabezado
         * de la tabla ya no está encima de nada, así que cada celda tiene que
         * poder decir de qué columna es. Lo pinta el CSS con `attr(data-col)`
         * y solo por debajo del corte. */
        (d.dolores || []).map(function (x) {
          return '<tr><td data-col="Dolor posible">' + esc(x.dolor) +
            '</td><td data-col="Evidencia">' +
            esc(x.evidencia_texto) + '</td><td data-col="Grado">' +
            (x.grado || []).map(function (g, i) {
              /* `grado_detalle` va pegado al PRIMER grado: «Lo cuenta ella ·
                 1 caso». Es lo que distingue un caso contado de una serie. */
              return '<span class="grado ' + (CLASE[g] || 'hip') + '">' +
                esc(g + (i === 0 && x.grado_detalle
                         ? ' · ' + x.grado_detalle : '')) + '</span>';
            }).join(' ') + '</td><td data-col="Pregunta para validarlo">' +
            esc('«' + (x.pregunta || '') + '»') +
            (x.nota_producto ? '<span class="s" style="display:block;' +
              'color:var(--ink3); font-size:12px">' + esc(x.nota_producto) +
              '</span>' : '') + '</td></tr>';
        }).join('') + '</tbody></table></div>'
      : noValido((d._no_validas || {}).dolores);
    return '<section class="porque-ella" aria-label="Dolores posibles">' +
      '<h2 style="font-size:21px">Dolores posibles y cómo validarlos</h2>' +
      cuerpo + '</section>';
  }

  /* ── 5 y 6 · Primer mensaje, canal, preguntas y objeción ──────────────── */
  function conversar(d) {
    var m = d.mensaje || {};
    if (!ok(d, 'mensaje')) {
      return '<section class="conversar" aria-label="Cómo abrirle la conversación">' +
        '<div><h2 style="font-size:21px">Cómo abrirle la conversación</h2>' +
        noValido((d._no_validas || {}).mensaje) + '</div><div></div></section>';
    }
    return '<section class="conversar" aria-label="Cómo abrirle la conversación">' +
      '<div style="display:grid; gap:12px; align-content:start">' +
      '<header style="display:grid; gap:4px"><p class="eyebrow">Primer mensaje · SMS</p>' +
      '<h2 style="font-size:21px">Cómo abrirle la conversación</h2></header>' +
      '<div class="mensaje" id="msg"><span class="tipo">SMS · editar los ' +
      '[corchetes] · pendiente de revisión de Compliance</span><p>' +
      esc((m.sms || {}).texto || '') + '</p></div>' +
      '<button class="copiar" id="btnCopiar" type="button">Copiar SMS</button>' +
      '<details class="src"><summary>Versión larga para email o DM</summary>' +
      '<div class="evid" id="msgLargo"><p>' + esc((m.largo_es || {}).texto || '') +
      '</p><p>' + esc((m.largo_en || {}).texto || '') + '</p></div></details>' +
      '<p class="muestra">No menciona sus transacciones ni sus relaciones con ' +
      'lenders. Solo usa lo que ella publica.</p></div>' +
      '<div class="lado-der">' +
      '<div><h3>Canal</h3><p style="font-size:14px; color:var(--ink2); ' +
      'margin-top:4px">' + esc((m.canal || {}).texto || '') + '</p></div>' +
      '<div><h3>Qué preguntarle en la llamada</h3><ol class="preguntas">' +
      (m.preguntas || []).map(function (p) {
        return '<li>' + esc(p.texto || p) + '</li>';
      }).join('') + '</ol></div>' +
      (m.objecion ? '<div class="objecion"><b>Objeción probable:</b> ' +
        esc(m.objecion.texto) + '</div>' : '') +
      '<p class="muestra">' + pendiente(_pendienteDe(d, 'LO asignado') ||
        'Qué LO de HOMESÍ la atiende.') + '</p></div></section>';
  }

  /* ── 7 · Producción ───────────────────────────────────────────────────── */
  /* Los KPIs, los trimestres, el loan mix, los lenders y la tabla los llena el
   * CÓDIGO; el lede, la nota del mix y «lo que significa» los escribe la IA.
   * Las dos formas se pintan aquí y no en dos plantillas: una sola plantilla
   * es lo que hace que la aceptación visual signifique algo. */
  function produccion(d) {
    var p = d.produccion || {};
    if (!p.kpis && !p.operaciones) {
      return '<section class="grid"><article class="mod col-full">' +
        '<header><p class="eyebrow">Model Match · Transactions</p>' +
        '<h2>Su producción</h2></header><p class="lede">' +
        pendiente('falta Transactions: sin esa pestaña no se sabe cuáles de ' +
                  'sus compras figuran como cash, y eso no se calcula por ' +
                  'diferencia') + '</p></article></section>';
    }
    var kpis = p.kpis || [];
    var maxTri = Math.max.apply(null,
      [1].concat((p.trimestres || []).map(function (t) { return t.n; })));
    var mix = p.loan_mix || [];
    var maxMix = Math.max.apply(null,
      [1].concat(mix.map(function (x) { return x.n; })));

    return '<section class="grid"><article class="mod col-full">' +
      '<header><p class="eyebrow">Model Match · Transactions</p>' +
      '<h2>Su producción y con quién financian sus buyers</h2>' +
      (ok(d, 'produccion') && p.lede
        ? '<p class="lede">' + esc(p.lede.texto) + '</p>' : '') +
      '</header>' +
      '<div class="hechos" style="grid-template-columns:repeat(4,minmax(0,1fr))">' +
      kpis.map(function (x) {
        /* El KPI llega escrito por el código y puede traer una fecha ISO --el
           último closing-- o un importe. Ninguna de las dos se muestra cruda:
           `2026-09-14` no es una fecha para leer, y `$5,3 M` con un espacio
           normal se parte en dos líneas. */
        var n = String(x.n);
        if (/^\d{4}-\d{2}-\d{2}$/.test(n)) n = fecha(n);
        n = n.replace(/\s/g, ' ');
        return '<div class="hecho"><div class="n">' +
          n.replace(/ ?\/ ?(.+)$/, '<small> / $1</small>') +
          '</div><div class="l">' + esc(x.l) + '</div></div>';
      }).join('') + '</div>' +
      '<div class="grid" style="gap:22px"><div class="bloque">' +
      '<h3>Buys por trimestre</h3><div class="trimestres">' +
      (p.trimestres || []).map(function (t) {
        return '<div class="tri' + (t.parcial ? ' parcial' : '') +
          '"><span class="col"><i style="height:' +
          Math.round(100 * t.n / maxTri) + '%"></i></span><b>' + t.n +
          '</b><span>' + esc(t.t || t.etiqueta) + (t.parcial ? '*' : '') +
          '</span></div>';
      }).join('') + '</div>' +
      /* La nota y el título los escribe el CÓDIGO, con las fechas y el conteo
         de verdad. Tenerlos fijos aquí era inventar una frase genérica encima
         de datos que la app ya sabe. */
      (p.trimestres_nota ? '<p class="muestra">' + esc(p.trimestres_nota) +
        '</p>' : '') +
      '<h3 style="margin-top:8px">' +
      esc(p.loan_mix_titulo || 'Loan type de sus buys') +
      '</h3><div class="barras">' +
      mix.map(function (x) {
        var pend = x.pendiente || x.tipo === 'Pendiente';
        return '<div class="barra"><span' + (pend ? ' class="pend"' : '') +
          '>' + esc(x.tipo || x.etiqueta) + '</span><span class="t"><i style="width:' +
          Math.round(100 * x.n / maxMix) + '%' +
          (pend ? '; background:var(--warn)' : '') +
          '"></i></span><span class="v">' + x.n + '</span></div>';
      }).join('') + '</div>' +
      (ok(d, 'produccion') && p.nota_loan_mix
        ? '<p class="muestra">' + esc(p.nota_loan_mix.texto) + '</p>' : '') +
      '</div><div class="bloque"><h3>Lenders y LOs de sus buyers</h3>' +
      '<div class="gente">' + (p.lenders || []).map(function (l) {
        return '<div class="persona"><span class="quien"><b>' + esc(l.lender) +
          '</b><span>' + esc(l.detalle || '') + '</span></span>' +
          /* «1 buy», no «1 buys». Un plural mal puesto en una ficha que el BD
             lee en voz alta se nota, y es gratis no ponerlo. */
          '<span class="cuantas">' + (l.n != null ? l.n : l.buys) +
          ((l.n != null ? l.n : l.buys) === 1 ? ' buy' : ' buys') +
          '</span></div>';
      }).join('') + '</div>' +
      /* Sobre cuántas financiadas se sabe el originador. Solo aparece cuando
         falta alguno: repetir que no falta nada es ruido en la única caja
         donde el BD busca un nombre. */
      (p.cobertura_lender
        ? '<p class="muestra">' + esc(p.cobertura_lender) + '</p>' : '') +
      (ok(d, 'produccion') && p.lo_que_significa
        ? '<p class="lectura"><b>Lo que significa:</b> ' +
          esc(p.lo_que_significa.texto) + '</p>' : '') +
      '</div></div>' + tablaOperaciones(p.operaciones) + '</article></section>';
  }

  function tablaOperaciones(ops) {
    /* El golden trae aquí un texto en vez de las filas: las pone el código
       desde `v_transacciones_current`. Se dice, en vez de pintar una tabla
       vacía que se leería como «no tiene operaciones». */
    if (typeof ops === 'string') {
      return '<details class="src"><summary>De dónde sale: sus transactions' +
        '</summary><p class="muestra" style="margin-top:6px">' +
        pendiente('la tabla la llena el código desde la base') + '</p></details>';
    }
    if (!(ops || []).length) return '';
    return '<details class="src"><summary>De dónde sale: sus ' + ops.length +
      ' transactions</summary><div class="tabla-wrap" style="margin-top:8px">' +
      /* `ops` no pinta nada por sí sola: es la marca de que esta tabla se
         apila en pantalla angosta, igual que la de dolores. La marca va en la
         plantilla y no en el CSS porque es la plantilla la que sabe si las
         celdas llevan `data-col`. */
      '<table class="ops"><thead><tr><th>Closing</th><th>Side</th><th>Zona</th>' +
      '<th class="num">Sold</th><th>Loan</th><th>Lender · LO</th></tr></thead>' +
      '<tbody>' + ops.map(function (o) {
        var loan;
        if (o.estado_prestamo === 'financiada') {
          loan = esc(o.tipo || '') + (o.tasa || o.enganche
            ? '<span class="s">' + (o.enganche_pct != null
                ? o.enganche_pct + ' % down · ' : '') +
              (o.tasa != null ? String(o.tasa).replace('.', ',') + ' %' : '') +
              '</span>' : '');
        } else if (o.estado_prestamo === 'cash_segun_mm') {
          loan = 'Cash';
        } else {
          loan = '<span class="pend">Pendiente: MM no tiene el loan</span>';
        }
        return '<tr><td data-col="Closing">' + esc(fecha(o.fecha)) +
          '</td><td data-col="Side"><span class="lado' +
          (o.lado === 'venta' ? ' venta' : '') + '">' +
          (o.lado === 'venta' ? 'Listing' : 'Buy') +
          '</span></td><td data-col="Zona">' +
          esc((o.zip || '') + (o.ciudad ? ' · ' + o.ciudad : '')) +
          '</td><td class="num" data-col="Sold">' + dinero(o.precio) +
          '</td><td data-col="Loan">' + loan +
          '</td><td data-col="Lender · LO">' + esc(o.lender || '—') +
          (o.lo_nombre ? '<span class="s">' + esc(o.lo_nombre) + '</span>' : '') +
          '</td></tr>';
      }).join('') + '</tbody></table></div>' +
      '<p class="muestra" style="margin-top:6px">«Cash» es lo que muestra ' +
      'Model Match en operaciones de más de 5 semanas. No se guardan los ' +
      'nombres de buyers ni de sellers, y de la dirección solo queda el ZIP.' +
      '</p></details>';
  }

  /* ── 8 · Instagram ────────────────────────────────────────────────────── */
  function instagram(d) {
    var ig = d.instagram || {};
    var e = ig.encabezado || {};
    if (!ok(d, 'instagram')) {
      return '<section class="grid"><article class="mod col-full"><header>' +
        '<h2>Qué dice en redes</h2></header>' +
        noValido((d._no_validas || {}).instagram) + '</article></section>';
    }
    /* El encabezado lo arma el código: puede llegar ya escrito o por partes. */
    var cabeceraIg = typeof e === 'string' ? e
      : 'Instagram · @' + (e.handle || '—') +
        (e.leido_en ? ' · leído el ' + fecha(e.leido_en) : '');
    return '<section class="grid"><article class="mod col-full"><header>' +
      '<p class="eyebrow">' + esc(cabeceraIg) + '</p>' +
      '<h2>Qué dice en redes y a quién le habla</h2>' +
      (ig.lede ? '<p class="lede">' + esc(ig.lede.texto) + '</p>' : '') +
      '</header><div class="grid" style="gap:22px"><div class="bloque">' +
      '<h3>A quién le habla</h3><div class="gente">' +
      (ig.a_quien_le_habla || []).map(function (b) {
        return '<div class="persona"><span class="quien"><b>' + esc(b.titulo) +
          '</b><span><q>' + esc(b.cita.texto_literal) + '</q> · ' +
          esc(fecha(b.cita.fecha)) +
          (b.cita.nota ? esc(', ' + b.cita.nota) : '') +
          '</span></span></div>';
      }).join('') + '</div>' +
      (ig.nota_listings ? '<p class="muestra">' + esc(ig.nota_listings.texto) +
        '</p>' : '') +
      (ig.idioma ? '<h3 style="margin-top:6px">Idioma</h3>' +
        '<p style="font-size:14px; color:var(--ink2)">' +
        esc(ig.idioma.texto) + '</p>' : '') +
      '</div><div class="bloque"><h3>Qué cuenta de sus clientes</h3>' +
      (ig.que_cuenta_de_sus_clientes || []).map(function (c) {
        return '<p class="cita"><q>' + esc(c.texto_literal) + '</q>' +
          '<span class="de">' + esc(fecha(c.fecha)) +
          (c.nota ? ' · ' + esc(c.nota) : '') + '</span></p>';
      }).join('') +
      (ig.comentarios ? '<h3 style="margin-top:6px">Comentarios de posibles ' +
        'clientes</h3><p style="font-size:14px; color:var(--ink2)">' +
        /* El «No encontramos ninguno.» lo pone la plantilla en negrita, pero
           el texto que escribe Cowork puede empezar por la misma frase, y
           entonces se lee dos veces seguidas. Se pone solo si no está ya:
           quitarlo del todo dejaría sin titular a las fichas donde la IA no lo
           escribe, y pedírselo al prompt no protege de la ficha ya guardada. */
        (ig.comentarios.hay_clientes ||
         /^no encontramos ninguno/i.test(String(ig.comentarios.texto || '')
                                         .trim())
          ? '' : '<b style="color:var(--ink)">No encontramos ninguno.</b> ') +
        esc(ig.comentarios.texto) + '</p><div class="chips">' +
        (ig.comentarios.chips || []).map(function (c) {
          return '<span class="chip">' + esc(c) + '</span>';
        }).join('') + '</div>' : '') +
      '</div></div></article></section>';
  }

  /* ── 9 · Contexto plegado ─────────────────────────────────────────────── */
  function contexto(d) {
    var c = d.contexto || {};
    if (!ok(d, 'contexto')) {
      return '<section class="colapsado" aria-label="Contexto de su zona">' +
        noValido((d._no_validas || {}).contexto) + '</section>';
    }
    /* Los títulos vienen en el JSON: «Mercado de Cook County» nombra el
       condado que se está mirando, y ponerlo fijo lo borraba. */
    var bloques = [];
    if (c.mercado_resumen) {
      bloques.push('<details><summary><b>' +
        esc(c.mercado_titulo || 'Mercado') + '</b> <span>· ' +
        esc(c.mercado_resumen.texto) + '</span></summary><p style="margin-top:6px">' +
        esc((c.mercado_texto || {}).texto || '') + '</p></details>');
    }
    if (c.census_resumen) {
      bloques.push('<details><summary><b>' +
        esc(c.census_titulo || 'Quién vive en su zona') + '</b> <span>· ' +
        esc(c.census_resumen.texto) + '</span></summary><p style="margin-top:6px">' +
        esc((c.census_texto || {}).texto || '') + '</p></details>');
    }
    if (!bloques.length) return '';
    return '<section class="colapsado" aria-label="Contexto de su zona">' +
      bloques.join('') + '</section>';
  }

  /* ── 10 · Fuentes ─────────────────────────────────────────────────────── */
  function fuentes(d) {
    var f = d.fuentes;
    var texto = typeof f === 'string' ? f : ((f || {}).texto || '');
    /* Los pendientes son `{item, texto_visible}`: en el pie va el item corto,
       y el texto largo lo usa quien lo necesite (el LO, en su sección). Una
       lista de frases largas al pie no se lee. */
    var items = (d.pendientes || []).map(function (p) {
      return typeof p === 'string' ? p : (p.item || p.texto_visible || '');
    }).filter(Boolean);
    return '<footer class="fuentes"><p><b>Fuentes:</b> ' + esc(texto) + '</p>' +
      '<p><b>Falta en esta ficha:</b> ' + esc(items.join(' · ')) +
      '</p></footer>';
  }

  /* TODAS las clases salen con `fv3-`, y se prefijan AQUÍ y no en cada
   * plantilla de cadena.
   *
   * Hay unas sesenta clases repartidas en diez funciones. Prefijarlas a mano
   * es acordarse sesenta veces, y la que se olvide no va a fallar: va a heredar
   * el estilo que la app le dé a ese nombre, que es exactamente cómo se rompió
   * --`.grid`, `.mod`, `.veredicto`, `.fila`, `.chip` y `.persona` existen en
   * las dos hojas-- y se ve raro sin decir por qué.
   *
   * Una sola pasada al final no se puede olvidar. */
  function prefijar(html) {
    return html.replace(/class="([^"]*)"/g, function (_, clases) {
      return 'class="' + clases.trim().split(/\s+/).filter(Boolean)
        .map(function (c) {
          return c.indexOf('fv3-') === 0 ? c : 'fv3-' + c;
        }).join(' ') + '"';
    });
  }

  /* La cabecera que pone la APP: cuándo se redactó la ficha, con qué versión,
   * el aviso de datos nuevos y el botón de pedir.
   *
   * Vivía FUERA de `.fv3-raiz`, en una tarjeta de la app, y por eso lo primero
   * que se veía al abrir la ficha estaba en la tipografía de la app y lo de
   * abajo en la de la maqueta. Aquí dentro hereda la de la ficha, que es lo
   * único que hace que «una sola familia de fuentes» sea cierto y no una
   * aspiración. El botón usa `.copiar`, que la maqueta ya define con
   * `font:inherit`. */
  function cabeceraApp(d) {
    if (!d._cabecera_version && !d._boton_pedir && !d._aviso_datos) return '';
    return '<div style="display:grid; gap:8px; justify-items:start">' +
      (d._cabecera_version
        ? '<p class="version">' + esc(d._cabecera_version) + '</p>' : '') +
      (d._aviso_datos
        ? '<p class="version" style="color:var(--warn); font-weight:600">' +
          esc(d._aviso_datos) + '</p>' : '') +
      (d._boton_pedir
        ? '<button class="copiar" id="btnPedir" type="button">' +
          esc(d._boton_pedir) + '</button>' : '') +
      '</div>';
  }

  function render(d) {
    d = d || {};
    return prefijar('<div class="raiz"><div class="wrap">' +
      cabeceraApp(d) +
      quienEs(d) + veredicto(d) + porQueElla(d) + dolores(d) + conversar(d) +
      produccion(d) + instagram(d) + contexto(d) + fuentes(d) +
      '</div></div>');
  }

  global.renderFichaV3 = render;
  global.fichaV3Utils = {esc: esc, fecha: fecha, dinero: dinero,
                         pendiente: pendiente, telefono: telefono,
                         legible: legible};
})(typeof window !== 'undefined' ? window : globalThis);
