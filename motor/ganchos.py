"""Los ganchos conversacionales del corpus, literales.

GENERADO por `scripts/generar_ganchos.py` desde las hojas `1 · Dolores` y
`4 · Nicho latino v2` del libro, columna `Gancho conversacional`. **No se
edita a mano.**

El gancho es la frase con la que el BD abre la conversacion. Una palabra
cambiada al copiar es una frase que ya no es la calibrada, y por eso no se
transcribe.

El enrutado
-----------
`MAPA` va de qualifier a ficha. Es una DECISION, no una derivacion: la matriz
no liga las dos cosas, y este mapa es el que venia del prototipo.

`P-Q01` tiene dos variantes segun la señal que lo activo -- ITIN o cuenta
propia-- porque el mismo dolor se abre distinto en cada caso.

Lo derivado va MARCADO
----------------------
`J-Q05` y `J-Q06` no tienen ficha con gancho propio. Su gancho es derivado y
`gancho_de()` lo devuelve con `derivado=True`, para que la pantalla no lo
presente como si viniera del corpus. Un gancho inventado que parece calibrado
es peor que uno que se declara inventado.
"""
from __future__ import annotations

from dataclasses import dataclass

#: ficha -> su gancho literal y de que hoja salio.
CORPUS: dict[str, dict] = {
    'G-N01': {
        'gancho': "Cuando un caso de ITIN se aprueba, ¿cuánto se demora en promedio comparado con uno normal? Lo pregunto porque la diferencia entre 'lo hacemos' y 'lo hacemos igual de rápido' es donde se cae casi todo.",
        'titulo': 'El cliente con ITIN que cierra como cualquier otro cliente',
        'hoja': '4 · Nicho latino v2',
    },
    'G-N02': {
        'gancho': 'Con clientes que tienen permiso de trabajo vigente, ¿puedes comprometer una fecha de cierre en la oferta o te toca dejarla abierta? Eso solo se responde de dos maneras y las dos dicen mucho.',
        'titulo': 'El permiso de trabajo deja de ser un asterisco',
        'hoja': '4 · Nicho latino v2',
    },
    'G-N03': {
        'gancho': "Cuando te rechazan un cliente por score, ¿te dan una ruta para volver o te dan un 'que arregle el crédito'? Lo segundo no es una respuesta, es un adiós.",
        'titulo': 'El score de 590 se vuelve una puerta, no un portazo',
        'hoja': '4 · Nicho latino v2',
    },
    'G-N04': {
        'gancho': "Te hago una pregunta rara: ¿en qué idioma le llegan los documentos a tus clientes? Todo el mundo vende 'atención en español' y casi nadie llega hasta el disclosure.",
        'titulo': 'El proceso completo en el idioma en que se hizo la venta',
        'hoja': '4 · Nicho latino v2',
    },
    'G-N05': {
        'gancho': 'En tu comunidad, ¿qué pesa más: cerrar un caso difícil o no haber prometido uno que se cayó? Casi siempre lo segundo, y casi nadie lo trabaja.',
        'titulo': 'Una promesa que puede sostener delante de su gente',
        'hoja': '4 · Nicho latino v2',
    },
    'G-N06': {
        'gancho': '¿Cuántas veces has explicado lo mismo este año? Me interesa porque casi ningún agente latino tiene ese trabajo contado, y suele ser la mitad de su semana.',
        'titulo': 'El trabajo de traducir dos mundos deja de ser gratis',
        'hoja': '4 · Nicho latino v2',
    },
    'P-001': {
        'gancho': 'Una curiosidad de oficio: ¿cuántas veces al mes terminas tú persiguiendo un talón de pago que ni siquiera es tu documento?',
        'titulo': 'El realtor terminó siendo el cobrador de talones de pago',
        'hoja': '1 · Dolores',
    },
    'P-002': {
        'gancho': '¿Te ha pasado que el agente del vendedor sabe más del avance de tu préstamo que tú?',
        'titulo': 'Le preguntan por el préstamo y no tiene cómo responder sin llamar',
        'hoja': '1 · Dolores',
    },
    'P-003': {
        'gancho': '¿Todavía te llegan documentos financieros de tus clientes por correo? Pregunto porque este año se han puesto creativos con eso.',
        'titulo': 'Documentos financieros viajando por correo, con el riesgo encima',
        'hoja': '1 · Dolores',
    },
    'P-004': {
        'gancho': '¿Cuántas veces este año un cliente tuyo te ha preguntado si el banco sabe lo que está haciendo?',
        'titulo': 'Le vuelven a pedir al cliente lo que ya había mandado',
        'hoja': '1 · Dolores',
    },
    'P-005': {
        'gancho': '¿Te ha tocado explicarle a un vendedor que el cierre se mueve por un error de tecleo? Es de las conversaciones más incómodas del oficio.',
        'titulo': 'Un error de tipeo en el 1003 que estalla en la recta final',
        'hoja': '1 · Dolores',
    },
    'P-006': {
        'gancho': '¿Cuánto se te demora probar que el enganche existe, cuando ya sabes perfectamente que existe?',
        'titulo': 'El enganche existe, pero probarlo toma días',
        'hoja': '1 · Dolores',
    },
    'P-007': {
        'gancho': '¿Sigue habiendo firmas en tu proceso que dependen de que alguien encuentre una impresora?',
        'titulo': 'Las divulgaciones se atrasan porque el comprador no tiene impresora',
        'hoja': '1 · Dolores',
    },
    'P-008': {
        'gancho': 'Cuando el préstamo de tu cliente se frena, ¿te enteras de qué lo frenó, o solo de que se frenó?',
        'titulo': 'No sabe qué documento está frenando el préstamo de su propio cliente',
        'hoja': '1 · Dolores',
    },
    'P-009': {
        'gancho': '¿Cuántas veces te ha cambiado el techo del cliente a mitad del proceso, cuando ya escogió casa?',
        'titulo': 'El poder de compra se mueve después de firmar el contrato',
        'hoja': '1 · Dolores',
    },
    'P-010': {
        'gancho': 'Cuando preguntas por un préstamo, ¿te dan una respuesta o te dan tres?',
        'titulo': 'Cada quien tiene su versión del expediente y ninguna es la buena',
        'hoja': '1 · Dolores',
    },
    'P-011': {
        'gancho': '¿Has notado que en temporada alta tus expedientes no se atrasan por complicados, sino por hacer fila?',
        'titulo': 'El equipo que arma su préstamo está ocupado renombrando archivos',
        'hoja': '1 · Dolores',
    },
    'P-012': {
        'gancho': 'Cuando escribes el plazo de cierre en una oferta, ¿lo eliges por estrategia o por miedo?',
        'titulo': 'No puede prometer una fecha de cierre porque no la controla nadie que él conozca',
        'hoja': '1 · Dolores',
    },
    'P-013': {
        'gancho': '¿Cuántas casas se te han ido este año esperando que salga una carta?',
        'titulo': 'La carta de preaprobación llega después de que la casa ya tiene otra oferta',
        'hoja': '1 · Dolores',
    },
    'P-014': {
        'gancho': '¿Cuántas cosas pueden salir mal en cuarenta días? Yo llevo la cuenta y sigue subiendo.',
        'titulo': 'Un cierre de más de cuarenta días es una apuesta abierta',
        'hoja': '1 · Dolores',
    },
    'P-015': {
        'gancho': '¿Tu prestamista ordena la tasación desde el día uno o espera a tener todo lo demás listo?',
        'titulo': 'Todo se hace en fila cuando podría hacerse al mismo tiempo',
        'hoja': '1 · Dolores',
    },
    'P-016': {
        'gancho': '¿Cuántos listados has dejado pasar este año solo porque pedían un plazo que tu prestamista no da?',
        'titulo': 'El vendedor exige cerrar rápido y él no tiene carril rápido',
        'hoja': '1 · Dolores',
    },
    'P-017': {
        'gancho': '¿Alguna vez un juego de muebles te tumbó un cierre? A mí me han contado esa historia demasiadas veces.',
        'titulo': 'El crédito del comprador cambia en los últimos diez días',
        'hoja': '1 · Dolores',
    },
    'P-018': {
        'gancho': 'Cuando mandas un caso que no es de manual, ¿alguien lo mira distinto o cae en la misma fila que todos?',
        'titulo': 'El caso complicado cae en la fila normal y ahí se queda',
        'hoja': '1 · Dolores',
    },
    'P-019': {
        'gancho': '¿Todavía se te corren cierres por cuadrar quién puede estar sentado en la mesa ese día?',
        'titulo': 'Coordinar la firma presencial es un problema logístico que nadie asume',
        'hoja': '1 · Dolores',
    },
    'P-020': {
        'gancho': '¿Has tenido que explicar una Closing Disclosure que traía un número que nadie sabía de dónde salió?',
        'titulo': 'Se entera de una tarifa mal cargada cuando ya está en la Closing Disclosure',
        'hoja': '1 · Dolores',
    },
    'P-021': {
        'gancho': '¿Te ha pasado ofrecer más que el que ganó y aun así perder? Es de las cosas que más me han contado este año.',
        'titulo': 'Su oferta se descarta antes de que alguien lea el precio',
        'hoja': '1 · Dolores',
    },
    'P-022': {
        'gancho': '¿Le has tenido que decir a un cliente que no retire la contingencia sabiendo que por eso van a perder la casa?',
        'titulo': 'La contingencia de financiamiento le resta puntos en cada oferta que escribe',
        'hoja': '1 · Dolores',
    },
    'P-023': {
        'gancho': '¿Cuántos clientes tienes que son solventes de sobra pero no tienen el dinero disponible el día que aparece la casa?',
        'titulo': 'Es solvente, pero no líquido, y el mercado solo entiende de líquido',
        'hoja': '1 · Dolores',
    },
    'P-024': {
        'gancho': '¿Has tenido vendedores que aceptan tu oferta y siguen mostrando la casa igual? Eso no es contra tu cliente.',
        'titulo': 'El vendedor no teme al comprador: teme al préstamo',
        'hoja': '1 · Dolores',
    },
    'P-025': {
        'gancho': 'En tu zona, ¿cuántas veces al año la tasación te reabre una negociación que ya estabas dando por cerrada?',
        'titulo': 'La tasación puede tumbar el trato y el comprador no tiene con qué cubrir la diferencia',
        'hoja': '1 · Dolores',
    },
    'P-026': {
        'gancho': '¿Cuántas ofertas escribiste el año pasado para tu mejor cliente antes de ganar una?',
        'titulo': 'Escribe ofertas que ya sabe que va a perder',
        'hoja': '1 · Dolores',
    },
    'P-027': {
        'gancho': '¿Has dejado de tomar listados de cierto precio porque sabes que el financiamiento se te complica ahí?',
        'titulo': 'Las casas de rango alto o no conformes se le quedan sin comprador financiado',
        'hoja': '1 · Dolores',
    },
    'P-028': {
        'gancho': '¿Te han dicho alguna vez que no aceptan FHA antes de mirar la oferta? ¿Cuántas veces este año?',
        'titulo': 'Su comprador es rechazado por el programa que usa, no por quién es',
        'hoja': '1 · Dolores',
    },
    'P-029': {
        'gancho': '¿El depósito de garantía en tu zona ya se volvió parte de la competencia, o todavía es solo un trámite?',
        'titulo': 'El depósito de garantía que piden es más de lo que el comprador puede mover hoy',
        'hoja': '1 · Dolores',
    },
    'P-030': {
        'gancho': '¿Cuántas veces has visto ganar a una oferta más baja solo porque cerraba antes?',
        'titulo': 'No puede ofrecer lo único que ese vendedor quería: cerrar en diez días',
        'hoja': '1 · Dolores',
    },
    'P-031': {
        'gancho': '¿Cuánta gente tienes en tu base que necesita mudarse hace rato y no se mueve porque todo su dinero está en su casa actual?',
        'titulo': 'El ahorro de su cliente está en las paredes de la casa donde vive',
        'hoja': '1 · Dolores',
    },
    'P-032': {
        'gancho': 'Cuando un cliente te dice que no quiere mudarse dos veces, ¿tienes con qué responderle o ahí se acaba la conversación?',
        'titulo': 'Mudarse dos veces con toda la familia es una razón suficiente para no mudarse',
        'hoja': '1 · Dolores',
    },
    'P-033': {
        'gancho': '¿Cuándo fue la última vez que te aceptaron una oferta contingente a venta? Esa es la pregunta que más incomoda en este mercado.',
        'titulo': 'La contingencia de venta previa hace que ni miren su oferta',
        'hoja': '1 · Dolores',
    },
    'P-034': {
        'gancho': '¿Cuántos de tus clientes están atrapados en su propia casa por una tasa buenísima que no quieren soltar?',
        'titulo': 'Sacar el enganche le costaría al cliente su hipoteca barata',
        'hoja': '1 · Dolores',
    },
    'P-035': {
        'gancho': '¿Cuántos clientes tuyos califican para dos hipotecas y aun así no duermen con la idea?',
        'titulo': 'Dos hipotecas al mismo tiempo es un pensamiento que nadie aguanta',
        'hoja': '1 · Dolores',
    },
    'P-036': {
        'gancho': '¿Cuánto le cuesta a tus clientes mudarse dos veces? Porque muchas veces ese número es el que decide la operación.',
        'titulo': 'La doble mudanza cuesta plata, tiempo y ganas',
        'hoja': '1 · Dolores',
    },
    'P-037': {
        'gancho': '¿Qué haces con el cliente que necesita moverse pero apenas lleva tres años en su casa?',
        'titulo': 'No tiene suficiente plusvalía para un puente normal',
        'hoja': '1 · Dolores',
    },
    'P-038': {
        'gancho': 'Cuando le ofreces un puente a un cliente, ¿le explican también cómo sale de él?',
        'titulo': 'Cuando por fin vende, le toca pagar la suscripción dos veces',
        'hoja': '1 · Dolores',
    },
    'P-039': {
        'gancho': '¿Alguna vez se te ha caído una cadena completa por un solo préstamo? Esa historia siempre la cuenta el broker, no el agente.',
        'titulo': 'Se le cae un eslabón intermedio y se le caen cuatro operaciones',
        'hoja': '1 · Dolores',
    },
    'P-040': {
        'gancho': '¿Qué pasa con tus clientes cuando el constructor mueve la fecha de entrega tres meses? ¿Quién paga esos meses?',
        'titulo': 'En obra nueva, el retraso de la construcción desalinea toda la operación',
        'hoja': '1 · Dolores',
    },
    'P-041': {
        'gancho': 'El número con el que sales a buscar casa, ¿quién lo firmó? ¿Un sistema o un suscriptor?',
        'titulo': 'Busca casas con un techo que nadie ha validado',
        'hoja': '1 · Dolores',
    },
    'P-042': {
        'gancho': '¿Te ha pasado que el mismo cliente califica para dos números distintos según a quién le mandes el archivo?',
        'titulo': 'El ingreso de su cliente vale distinto según quién lo mire',
        'hoja': '1 · Dolores',
    },
    'P-043': {
        'gancho': '¿Cuántos de tus compradores primerizos reciben ayuda de la familia para el enganche? Esa ayuda casi siempre trae cola.',
        'titulo': 'El enganche llegó como regalo de la familia y ahora hay que explicarlo',
        'hoja': '1 · Dolores',
    },
    'P-044': {
        'gancho': '¿En tu zona el seguro ya está tumbando préstamos? Porque en varios mercados ya es la causa número uno.',
        'titulo': 'El seguro y los impuestos definitivos le sacan el DTI de rango al final',
        'hoja': '1 · Dolores',
    },
    'P-045': {
        'gancho': '¿Cuántas veces ha aparecido una deuda vieja justo al final? Casi nunca es mentira del cliente: es olvido.',
        'titulo': 'Aparece una deuda que el comprador no recordaba tener',
        'hoja': '1 · Dolores',
    },
    'P-046': {
        'gancho': 'Cuando recibes cinco ofertas, ¿miras las cartas de preaprobación o ya diste por hecho que todas dicen lo mismo?',
        'titulo': 'Su carta de preaprobación no pesa lo que debería pesar',
        'hoja': '1 · Dolores',
    },
    'P-047': {
        'gancho': '¿Cuántos sábados del año se te van mostrando casas que después resulta que no eran para ese cliente?',
        'titulo': 'Lleva al cliente a ver casas que nunca va a poder comprar',
        'hoja': '1 · Dolores',
    },
    'P-048': {
        'gancho': 'De los contratos que firmaste el año pasado, ¿cuántos llegaron a la mesa de cierre? Ese número dice más que el de ofertas escritas.',
        'titulo': 'El contrato se cae en la recta final, que es donde más duele',
        'hoja': '1 · Dolores',
    },
    'P-049': {
        'gancho': '¿Cuál es el documento que más se demora en tus expedientes? Casi siempre es uno que no depende de tu cliente.',
        'titulo': 'Los documentos que dependen de terceros se piden demasiado tarde',
        'hoja': '1 · Dolores',
    },
    'P-050': {
        'gancho': 'Cuando tu cliente firma contrato, ¿el préstamo arranca donde quedó o arranca de cero otra vez?',
        'titulo': 'Todo el trabajo previo se descarta y la suscripción empieza de cero',
        'hoja': '1 · Dolores',
    },
    'P-051': {
        'gancho': 'Una pregunta de curiosidad: en tu corredor, ¿cuántos de tus contratos del último año se atrasaron esperando el avalúo de una casa prácticamente idéntica a la de al lado?',
        'titulo': 'El avalúo presencial como peaje obligatorio de cada expediente',
        'hoja': '1 · Dolores',
    },
    'P-052': {
        'gancho': 'Me da curiosidad tu experiencia: ¿te ha pasado que el avalúo de una casa tuya salió con comparables de otro sector y tuviste que defender tu propio CMA delante del dueño?',
        'titulo': 'El valor del inmueble depende de a quién le tocó el expediente',
        'hoja': '1 · Dolores',
    },
    'P-053': {
        'gancho': 'Sin ánimo de abrir heridas: ¿cuál fue la última negociación que ya tenías cerrada y te tocó volver a sentar a las dos partes por un avalúo bajo?',
        'titulo': 'El precio pactado se reabre cuando ya estaba cerrado',
        'hoja': '1 · Dolores',
    },
    'P-054': {
        'gancho': 'Te hago una pregunta incómoda: ¿cuántas veces te ha tocado adelantar tú el avalúo de un cliente para que no se te caiga el expediente?',
        'titulo': 'El avalúo compite con el enganche por el efectivo del comprador',
        'hoja': '1 · Dolores',
    },
    'P-055': {
        'gancho': '¿En tu zona hay suficientes tasadores? Pregunto porque he visto agentes de mercados como el tuyo comprometiendo fechas de cierre que dependen de la agenda de una sola persona.',
        'titulo': 'No hay tasadores disponibles y el calendario se congela',
        'hoja': '1 · Dolores',
    },
    'P-056': {
        'gancho': 'Curiosidad honesta: cuando aconsejas ofertar por encima del precio de lista, ¿tú y tu cliente ya saben, antes de firmar, quién cubre la diferencia si el avalúo sale bajo?',
        'titulo': 'Ofertar por encima del precio de lista sin un plan para la brecha',
        'hoja': '1 · Dolores',
    },
    'P-057': {
        'gancho': '¿Alguna vez te han pedido efectivo extra en la semana del cierre porque el avalúo movió el LTV? Me interesa cómo lo manejaste con la familia.',
        'titulo': 'Después del avalúo bajo, el LTV se rompe y aparece un efectivo que nadie previó',
        'hoja': '1 · Dolores',
    },
    'P-058': {
        'gancho': 'Cuando te llega un avalúo que sabes que está mal, ¿tienes a dónde llevar tus comparables, o se queda en un correo que nadie responde?',
        'titulo': 'Un informe con errores y ningún canal para impugnarlo',
        'hoja': '1 · Dolores',
    },
    'P-059': {
        'gancho': '¿Los tasadores que te asignan conocen tu vecindario, o te toca explicarles por qué esta cuadra no se compara con la de allá?',
        'titulo': 'Un tasador de fuera evalúa un micro-mercado que no conoce',
        'hoja': '1 · Dolores',
    },
    'P-060': {
        'gancho': 'Cuando un expediente tuyo no califica a exención, ¿te ofrecen algo entre el waiver y el avalúo completo, o te mandan directo a la cola de tres semanas?',
        'titulo': 'El expediente no califica a exención pero tampoco puede esperar tres semanas',
        'hoja': '1 · Dolores',
    },
    'P-061': {
        'gancho': '¿Te ha pasado que tu mejor inversor es el que menos califica en el banco? Me interesa cómo le explicas eso a alguien que ya tiene rentas funcionando.',
        'titulo': 'El inversor con más propiedades es el que menos califica',
        'hoja': '1 · Dolores',
    },
    'P-062': {
        'gancho': 'Con tus inversores, ¿en qué número de compra se les acaba el cupo? Me llama la atención cuántos agentes ya saben la respuesta de memoria.',
        'titulo': 'Cada compra que gana le cierra la puerta a la siguiente',
        'hoja': '1 · Dolores',
    },
    'P-063': {
        'gancho': '¿Cuántas horas al mes se te van persiguiendo documentos fiscales de clientes con varias empresas? Pregunto porque casi nadie lo cuenta y casi todos lo hacen.',
        'titulo': 'Tres empresas, dos Schedule E y un expediente que no avanza',
        'hoja': '1 · Dolores',
    },
    'P-064': {
        'gancho': '¿Has tenido un cliente que llegó a las diez propiedades financiadas? Me interesa qué pasó con él después, porque casi siempre siguió comprando.',
        'titulo': 'El tope de diez propiedades corta la relación en su mejor momento',
        'hoja': '1 · Dolores',
    },
    'P-065': {
        'gancho': 'Tus inversores que compran bajo LLC, ¿pueden cerrar directo a nombre de la entidad o les toca cerrar personal y transferir después?',
        'titulo': 'El inversor quiere comprar como LLC y le toca comprar como persona',
        'hoja': '1 · Dolores',
    },
    'P-066': {
        'gancho': 'En tu zona, ¿cuántos compradores buscan renta corta? Me interesa porque los bancos siguen pidiendo un contrato anual que ese modelo nunca va a tener.',
        'titulo': 'El Airbnb produce, pero el banco no lo ve',
        'hoja': '1 · Dolores',
    },
    'P-067': {
        'gancho': 'Tus inversores que compran para remodelar, ¿arrancan pagando capital desde el primer mes aunque la casa todavía esté en obra?',
        'titulo': 'La cuota mensual se come el rendimiento del primer año',
        'hoja': '1 · Dolores',
    },
    'P-068': {
        'gancho': 'Cuando vendes obra nueva a inversores, ¿cómo demuestran la renta de una casa que todavía nadie ha habitado?',
        'titulo': 'La casa vacía no tiene contrato que mostrar',
        'hoja': '1 · Dolores',
    },
    'P-069': {
        'gancho': '¿Te llegan compradores de tu país que tienen el dinero pero no tienen historial acá? Me interesa saber qué haces con ellos hoy.',
        'titulo': 'El comprador extranjero tiene el dinero y no tiene historial',
        'hoja': '1 · Dolores',
    },
    'P-070': {
        'gancho': '¿Cuántos de tus inversores no venden solo por el impuesto a la ganancia? Pregunto porque ahí hay dos transacciones dormidas en cada uno.',
        'titulo': 'La venta del inversor se frena por el impuesto y se pierden dos transacciones',
        'hoja': '1 · Dolores',
    },
    'P-071': {
        'gancho': "¿Cuántos clientes tienes guardados esperando 'juntar el enganche'? Me interesa cuántos de ellos ya pagan un arriendo más alto que la cuota que tendrían.",
        'titulo': 'Gana bien, paga arriendo puntual y no tiene el enganche',
        'hoja': '1 · Dolores',
    },
    'P-072': {
        'gancho': '¿En qué momento del proceso tus clientes se enteran del total real de costos de cierre? Me llama la atención cuántos expedientes se caen en esa semana.',
        'titulo': 'Califica, tiene el enganche, y lo tumban los costos de cierre',
        'hoja': '1 · Dolores',
    },
    'P-073': {
        'gancho': 'Cuando un listado tuyo no se mueve, ¿la primera conversación con el dueño es bajar el precio? Me interesa qué tan seguido la objeción real era la cuota.',
        'titulo': 'Para mover el inmueble hay que bajar el precio de lista',
        'hoja': '1 · Dolores',
    },
    'P-074': {
        'gancho': '¿Tus compradores se enfrían al ver la cuota? Me interesa si alguna vez les has mostrado los dos primeros años calculados a una tasa más baja.',
        'titulo': 'El comprador podrá pagarla en dos años, pero tiene que firmar hoy',
        'hoja': '1 · Dolores',
    },
    'P-075': {
        'gancho': '¿Has tenido compradores que dicen que la cuota sí la aguantan, pero no el primer año completo con mudanza y muebles encima?',
        'titulo': 'Solo necesita respirar el primer año',
        'hoja': '1 · Dolores',
    },
    'P-076': {
        'gancho': 'Cuando un listado pasa de los dos meses, ¿qué conversación tienes con el dueño? Me interesa si alguien te ha planteado usar esa misma plata sin tocar el precio.',
        'titulo': 'El listado lleva meses parado y el vendedor ya solo piensa en rebajar',
        'hoja': '1 · Dolores',
    },
    'P-077': {
        'gancho': 'Cuando hay concesiones del vendedor sobre la mesa, ¿alguien pregunta primero cuántos años piensa quedarse la familia en esa casa?',
        'titulo': 'Le dieron alivio temporal a quien se va a quedar veinte años',
        'hoja': '1 · Dolores',
    },
    'P-078': {
        'gancho': '¿Te han preguntado qué pasa con la plata del buydown si el cliente refinancia antes? Es la pregunta que más veces he visto frenar una firma.',
        'titulo': 'El miedo a perder la plata del buydown si bajan las tasas',
        'hoja': '1 · Dolores',
    },
    'P-079': {
        'gancho': '¿Sabes cuáles de los programas de ayuda de tu zona se pueden apilar entre sí? Pregunto porque casi nadie tiene esa lista y casi todos la necesitan.',
        'titulo': 'Los programas existen, están dispersos y nadie los combina',
        'hoja': '1 · Dolores',
    },
    'P-080': {
        'gancho': '¿Cruzas tu búsqueda de propiedades con el mapa de distritos censales elegibles? Es un filtro que a varios agentes les cambió qué casas muestran primero.',
        'titulo': 'La ayuda depende de la cuadra y la búsqueda no lo tiene en cuenta',
        'hoja': '1 · Dolores',
    },
    'P-081': {
        'gancho': 'En tu cartera, ¿cuántos clientes facturan bien y declaran poco después de deducciones? Me interesa qué haces hoy con ellos.',
        'titulo': 'Su cliente gana bien y en el papel gana poco',
        'hoja': '1 · Dolores',
    },
    'P-082': {
        'gancho': 'Cuando te rechazan un cliente por puntaje, ¿te dicen si fue la norma federal o la política interna del banco? Casi nunca lo distinguen, y la diferencia es todo.',
        'titulo': 'El overlay del banco rechaza lo que la norma federal permite',
        'hoja': '1 · Dolores',
    },
    'P-083': {
        'gancho': '¿Trabajas compradores con beneficio VA? Me interesa si te han rechazado alguno por DTI sin haberlo corrido bajo las pautas del propio programa.',
        'titulo': 'El veterano tiene ingreso estable y el DTI lo saca',
        'hoja': '1 · Dolores',
    },
    'P-084': {
        'gancho': '¿Alguna vez te han evaluado un cliente por lo que le queda al mes, y no solo por el porcentaje de sus deudas? Se llama ingreso residual y cambia muchos casos.',
        'titulo': 'El ratio dice que no puede y la plata que le queda dice que sí',
        'hoja': '1 · Dolores',
    },
    'P-085': {
        'gancho': '¿Cuántos clientes tuyos están ahorrando un enganche que quizá no necesitan? En perfiles militares esa conversación se puede acortar mucho.',
        'titulo': 'Le exigen ahorrar un enganche que su beneficio no requiere',
        'hoja': '1 · Dolores',
    },
    'P-086': {
        'gancho': '¿Te llegan compradores que trabajan en plataformas y no tienen W-2? Me interesa saber dónde los mandas hoy.',
        'titulo': 'Gana de cinco fuentes y ninguna es un W-2',
        'hoja': '1 · Dolores',
    },
    'P-087': {
        'gancho': '¿Cuántos listados tuyos se estancan por el estado de la casa y no por el precio? Me interesa cuántos compradores has visto irse por no poder financiar los arreglos.',
        'titulo': 'La casa no se vende porque no se puede hipotecar',
        'hoja': '1 · Dolores',
    },
    'P-088': {
        'gancho': 'Cuando tu cliente llega con el 10%, ¿le muestran más de una forma de estructurar el préstamo, o solo una con PMI?',
        'titulo': 'Tiene el 10% y le toca elegir entre el PMI y quedarse sin reservas',
        'hoja': '1 · Dolores',
    },
    'P-089': {
        'gancho': '¿Tienes clientes que se salieron del mercado después de una quiebra o una ejecución? Muchos ya cumplieron el plazo y no lo saben.',
        'titulo': 'Ya pasaron los dos años y él sigue creyendo que no puede',
        'hoja': '1 · Dolores',
    },
    'P-090': {
        'gancho': '¿Has tenido un cierre donde el título estaba a nombre de una LLC? Me interesa cómo lo resolvieron ese día, porque suele aparecer en el peor momento.',
        'titulo': 'La LLC del cliente convierte el cierre en un problema',
        'hoja': '1 · Dolores',
    },
    'P-091': {
        'gancho': 'Cuando publicas un listado nuevo, ¿cuánto tarda en estar lista la pieza gráfica? Me interesa cuántos primeros fines de semana se te van sin material.',
        'titulo': 'Cada listado nuevo exige rehacer las piezas desde cero',
        'hoja': '1 · Dolores',
    },
    'P-092': {
        'gancho': 'Tu audiencia, cuando le gusta una casa tuya, ¿a dónde la mandas? Me interesa quién se queda con el dato de contacto al final.',
        'titulo': 'Quiere una página por propiedad y no tiene quién se la haga',
        'hoja': '1 · Dolores',
    },
    'P-093': {
        'gancho': 'En tus open houses, cuando preguntan cuánto sería al mes, ¿tienes algo impreso que entregar? Esa pregunta suele ser el momento de mayor intención de todo el sábado.',
        'titulo': 'En el open house nadie sabe cuánto pagaría al mes',
        'hoja': '1 · Dolores',
    },
    'P-094': {
        'gancho': 'Las mensualidades que publicas en tus piezas, ¿se actualizan solas o quedan congeladas? Pregunto porque ahí hay un tema de confianza y también de cumplimiento.',
        'titulo': 'La mensualidad publicada ya no es la de hoy',
        'hoja': '1 · Dolores',
    },
    'P-095': {
        'gancho': 'De las familias a las que les entregaste llaves hace dos años, ¿con cuántas sigues hablando? Es la pregunta que más incomoda y más plata mueve.',
        'titulo': 'A los dos años el cliente ya no se acuerda de su nombre',
        'hoja': '1 · Dolores',
    },
    'P-096': {
        'gancho': 'Cuando te preguntan por escuelas y plusvalía de un vecindario, ¿respondes con datos o de memoria? Me interesa cuánto tiempo te tomaría tener eso listo por zona.',
        'titulo': 'Le piden que sea el experto del barrio y las horas no le dan',
        'hoja': '1 · Dolores',
    },
    'P-097': {
        'gancho': '¿Has hecho talleres para compradores primerizos? Me interesa quién puso la plata y quién explicó la parte financiera.',
        'titulo': 'Prospectar solo le sale caro y le rinde poco',
        'hoja': '1 · Dolores',
    },
    'P-098': {
        'gancho': 'En la publicidad que compartes con tu oficial de préstamo, ¿hay un criterio escrito de quién paga qué porcentaje? Es la pregunta que hace un auditor y casi nadie tiene la respuesta a la mano.',
        'titulo': 'No sabe si la publicidad compartida que hace es legal',
        'hoja': '1 · Dolores',
    },
    'P-099': {
        'gancho': 'Los leads que te dicen que no califican, ¿a dónde van? Pregunto porque casi siempre son los mismos que compran doce meses después, con otro.',
        'titulo': 'Los leads que no calificaron hoy se pierden para siempre',
        'hoja': '1 · Dolores',
    },
    'P-100': {
        'gancho': '¿Cuánto tiempo llevas publicando seguido sin parar? Me interesa qué pasa con tu alcance cada vez que te toca desaparecer dos semanas.',
        'titulo': 'Mantener presencia constante en redes cuesta más de lo que puede',
        'hoja': '1 · Dolores',
    },
    'P-N01': {
        'gancho': 'Una curiosidad: cuando mandas un cliente que declara con ITIN, ¿te rechazan el caso o te rechazan la llamada? La diferencia dice mucho del lender.',
        'titulo': 'El ITIN se lee como una ausencia y no como lo que es',
        'hoja': '4 · Nicho latino v2',
    },
    'P-N02': {
        'gancho': "¿Te pasa que en los comentarios siempre aparece el mismo 'yo no puedo porque…'? Me interesa saber cuántos de esos crees que sí podrían y nunca te lo preguntan en privado.",
        'titulo': 'El comprador ya se dijo que no antes de llegar',
        'hoja': '4 · Nicho latino v2',
    },
    'P-N03': {
        'gancho': 'Sin que suene a examen: ¿hay algún tipo de cliente que ya ni siquiera mandas a calificar? Casi todos los agentes tienen uno, y casi siempre es el que más cambió de reglas en los últimos dos años.',
        'titulo': 'Dejó de mostrarle casas porque supuso que no iba a poder',
        'hoja': '4 · Nicho latino v2',
    },
    'P-N04': {
        'gancho': "Cuando mandas un cliente con permiso de trabajo vigente, ¿te dan una fecha de cierre o te dan un 'déjame consultar'? Me interesa cuál de las dos recibes más seguido.",
        'titulo': 'Tiene permiso de trabajo vigente y lo tratan como si fuera provisional',
        'hoja': '4 · Nicho latino v2',
    },
    'P-N05': {
        'gancho': '¿Cuántos de tus compradores tienen score bajo no porque hayan pagado mal, sino porque nunca les midieron nada? Es un caso distinto y casi nadie lo trata distinto.',
        'titulo': 'El score dice 590 y la historia dice otra cosa',
        'hoja': '4 · Nicho latino v2',
    },
    'P-N06': {
        'gancho': '¿Tus clientes te llaman a ti cuando les llega un documento del banco? Me interesa cuántas horas a la semana estás traduciendo papeles que no escribiste.',
        'titulo': 'El proceso está en inglés aunque la venta haya sido en español',
        'hoja': '4 · Nicho latino v2',
    },
    'P-N07': {
        'gancho': 'Pregunta incómoda pero útil: ¿en qué momento del proceso te enteras de cómo cobra realmente tu cliente? Casi siempre es demasiado tarde para servir de algo.',
        'titulo': 'El dinero existe pero no pasó por el banco',
        'hoja': '4 · Nicho latino v2',
    },
    'P-N08': {
        'gancho': '¿Cuántas de tus familias compradoras tienen tres o cuatro entradas de dinero en la misma casa? Me interesa cuánto de eso te reconocen hoy al calificar.',
        'titulo': 'Cinco ingresos en una casa y el sistema solo cuenta uno',
        'hoja': '4 · Nicho latino v2',
    },
    'P-N09': {
        'gancho': 'Me llama la atención algo del mercado latino: no cuesta encontrar al comprador, cuesta que confíe. ¿Cuántas semanas te toma en promedio que un cliente nuevo te entregue papeles?',
        'titulo': 'No cree que el sistema sea para él, y convencerlo cuesta meses',
        'hoja': '4 · Nicho latino v2',
    },
    'P-N10': {
        'gancho': 'Trabajar con tu propia comunidad tiene un lado que nadie menciona: cuando un caso se cae, se entera más gente que cuando uno se cierra. ¿Te ha pasado?',
        'titulo': 'Su reputación se paga con cada caso que muere',
        'hoja': '4 · Nicho latino v2',
    },
}

#: qualifier -> ficha. La DECISION de enrutado, del prototipo.
MAPA: dict[str, str] = {
    "P-Q01": "P-082",
    "P-Q06": "P-074",
    "P-Q07": "P-023",
    "P-Q09": "P-062",
    "P-Q10": "P-091",
    "P-Q11": "P-095",
    "P-Q12": "P-013",
    "P-Q13": "P-N10",
    "P-Q14": "P-N06",
    "P-Q17": "P-083",
    "P-Q19": "P-089",
    "P-Q20": "P-086",
    "P-Q21": "P-097",
}

#: `P-Q01` se abre distinto segun que señal lo activo. El mismo dolor -- el
#: lender rechaza el caso de nicho-- no se conversa igual con quien declara
#: ITIN que con quien declara cuenta propia.
VARIANTES: dict[str, list[tuple[str, str]]] = {
    "P-Q01": [("ev2_itin", "P-N01"), ("ev2_self_employed", "P-081")],
}

#: Los que NO tienen ficha con gancho propio. Su texto es derivado y se dice.
DERIVADOS: dict[str, str] = {
    "J-Q05": "¿Qué parte del proceso te toca explicar tú, que debería explicar "
             "el lender?",
    "J-Q06": "¿Cuántas veces al mes te enteras del avance de un préstamo por "
             "el cliente y no por el originador?",
}

#: `J-Q01` es compuerta: no se conversa.
NO_SE_CONVERSA = ("J-Q01",)


@dataclass
class Gancho:
    texto: str
    ficha: str | None
    fuente: str
    derivado: bool = False


def gancho_de(qualifier: str, señales: dict | None = None) -> Gancho | None:
    """El gancho de un qualifier, con su procedencia declarada.

    Devuelve None cuando el qualifier no se conversa (las compuertas) o cuando
    no hay ni ficha ni derivado -- que es un dato, no un error: significa que
    el enrutado no lo cubre y la pantalla tiene que poder decirlo.
    """
    if qualifier in NO_SE_CONVERSA:
        return None

    ficha = MAPA.get(qualifier)
    for campo, alterna in VARIANTES.get(qualifier, []):
        if (señales or {}).get(campo):
            ficha = alterna
            break

    if ficha and ficha in CORPUS:
        c = CORPUS[ficha]
        return Gancho(texto=c["gancho"], ficha=ficha,
                      fuente="ficha %s del corpus · %s" % (ficha, c["hoja"]),
                      derivado=False)

    if qualifier in DERIVADOS:
        return Gancho(
            texto=DERIVADOS[qualifier], ficha=None,
            fuente="DERIVADO: %s no tiene ficha con gancho propio en el corpus"
                   % qualifier,
            derivado=True)
    return None
