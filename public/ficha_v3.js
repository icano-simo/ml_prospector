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
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;',
              "'": '&#39;'}[c];
    });
  }

  /* `2026-03-11` se muestra como 11 mar 2026, no como 10.
   *
   * `new Date('2026-03-11')` se parsea como MEDIANOCHE UTC, y al formatearla
   * en hora local --Colombia es UTC-5-- sale el día anterior. Toda la ficha
   * está llena de fechas de closings y de posts, así que el error no era una:
   * eran todas, siempre un día antes, y siempre plausible. */
  function fecha(iso) {
    if (!iso) return '';
    var s = String(iso);
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
    var d = m ? new Date(+m[1], +m[2] - 1, +m[3]) : new Date(s);
    if (isNaN(d)) return s.slice(0, 10);
    return d.toLocaleDateString('es', {day: 'numeric', month: 'short',
                                       year: 'numeric'});
  }

  function dinero(n) {
    if (n == null) return '—';
    if (n >= 1e6) return '$' + (n / 1e6).toFixed(1).replace('.', ',') + 'M';
    if (n >= 1e3) return '$' + Math.round(n / 1e3) + 'K';
    return '$' + n;
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
    var ETIQUETA = {telefono: 'Teléfono', email: 'Email', oficina: 'Oficina',
                    direccion: 'Oficina', instagram: 'Instagram', web: 'Web',
                    otro: 'Otro'};
    var filas = Object.keys(contactos).map(function (k) {
      return '<div class="fila"><span class="k">' + esc(ETIQUETA[k] || k) +
        '</span><span class="v">' + contactos[k].map(function (x) {
          /* `difiere` significa que el dato está en UNA sola fuente y no
             coincide con el resto. Se dice, no se marca solo con un color: un
             color sin texto obliga a adivinar qué quiere decir. */
          return '<span class="dato"><span class="val">' + esc(x.valor) +
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
      '<span class="pendiente">' + esc(prio) + '</span></div>' + cuerpo +
      '</section>';
  }

  /* ── 4 · Dolores posibles ─────────────────────────────────────────────── */
  function dolores(d) {
    var CLASE = {'Dato': 'dato', 'Lo cuenta ella': 'ella',
                 'Hipótesis': 'hip', 'Hipótesis el porqué': 'hip'};
    var cuerpo = ok(d, 'dolores')
      ? '<div class="dolores-wrap"><table class="dolores"><thead><tr>' +
        '<th>Dolor posible</th><th>Evidencia</th><th>Grado</th>' +
        '<th>Pregunta para validarlo</th></tr></thead><tbody>' +
        (d.dolores || []).map(function (x) {
          return '<tr><td>' + esc(x.dolor) + '</td><td>' +
            esc(x.evidencia_texto) + '</td><td>' +
            (x.grado || []).map(function (g, i) {
              /* `grado_detalle` va pegado al PRIMER grado: «Lo cuenta ella ·
                 1 caso». Es lo que distingue un caso contado de una serie. */
              return '<span class="grado ' + (CLASE[g] || 'hip') + '">' +
                esc(g + (i === 0 && x.grado_detalle
                         ? ' · ' + x.grado_detalle : '')) + '</span>';
            }).join(' ') + '</td><td>' + esc('«' + (x.pregunta || '') + '»') +
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
        return '<div class="hecho"><div class="n">' +
          String(x.n).replace(/\s\/\s(.+)$/, '<small> / $1</small>') +
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
      '<table><thead><tr><th>Closing</th><th>Side</th><th>Zona</th>' +
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
        return '<tr><td>' + esc(fecha(o.fecha)) + '</td><td><span class="lado' +
          (o.lado === 'venta' ? ' venta' : '') + '">' +
          (o.lado === 'venta' ? 'Listing' : 'Buy') + '</span></td><td>' +
          esc((o.zip || '') + (o.ciudad ? ' · ' + o.ciudad : '')) +
          '</td><td class="num">' + dinero(o.precio) + '</td><td>' + loan +
          '</td><td>' + esc(o.lender || '—') +
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
        (ig.comentarios.hay_clientes ? '' :
          '<b style="color:var(--ink)">No encontramos ninguno.</b> ') +
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

  function render(d) {
    d = d || {};
    return '<div class="wrap">' +
      (d._cabecera_version
        ? '<p class="version">' + esc(d._cabecera_version) + '</p>' : '') +
      quienEs(d) + veredicto(d) + porQueElla(d) + dolores(d) + conversar(d) +
      produccion(d) + instagram(d) + contexto(d) + fuentes(d) +
      '</div>';
  }

  global.renderFichaV3 = render;
  global.fichaV3Utils = {esc: esc, fecha: fecha, dinero: dinero,
                         pendiente: pendiente};
})(typeof window !== 'undefined' ? window : globalThis);
