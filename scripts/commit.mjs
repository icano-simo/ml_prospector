#!/usr/bin/env node
/* Commitea con el mensaje de un ARCHIVO, y lo lee de vuelta para comprobarlo.
 *
 *     node scripts/commit.mjs <archivo-del-mensaje> [--amend]
 *
 * Por qué existe
 * --------------
 * El hook `sin-texto-al-shell` bloquea `git commit -m "<texto>"` y manda usar
 * esto. Hasta hoy el archivo no estaba en el repo, así que el hook apuntaba a
 * una herramienta que no existía y la única salida era `git commit -F`, que es
 * correcto pero no comprueba nada.
 *
 * La diferencia con `-F` a secas: esto LEE EL MENSAJE DE VUELTA con
 * `git log -1 --format=%B` y lo compara contra el archivo. Si no coincide,
 * revierte el commit y falla.
 *
 * Es la misma lección de siempre: que un comando salga con 0 no prueba que el
 * texto llegó entero. Los backticks del mensaje se sustituyen como comandos y
 * dejan huecos; el único rastro es un `command not found` que se lee como
 * ruido. Aquí el hueco hace fallar el commit.
 */
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

function git(args, opciones = {}) {
  return execFileSync('git', args, { encoding: 'utf8', ...opciones });
}

const [, , ruta, ...resto] = process.argv;
if (!ruta) {
  console.error('uso: node scripts/commit.mjs <archivo-del-mensaje> [--amend]');
  process.exit(2);
}

const mensaje = readFileSync(ruta, 'utf8');
if (!mensaje.trim()) {
  console.error('el archivo del mensaje está vacío: ' + ruta);
  process.exit(2);
}

/* El asunto: la primera línea. Si pasa de 72 caracteres se avisa y no se
   bloquea -- es una convención, no una regla de corrección. */
const asunto = mensaje.split('\n', 1)[0];
if (asunto.length > 72) {
  console.error('aviso: el asunto tiene %d caracteres (>72)', asunto.length);
}

const antes = git(['rev-parse', 'HEAD']).trim();
git(['commit', '-F', ruta, ...resto], { stdio: 'inherit' });

/* ── LA COMPROBACIÓN, LEYENDO DE GIT Y NO DE LA SALIDA DEL COMANDO ──────── */
const guardado = git(['log', '-1', '--format=%B']);
const norm = (s) => s.replace(/\r\n/g, '\n').replace(/\s+$/g, '');
if (norm(guardado) !== norm(mensaje)) {
  console.error('');
  console.error('EL MENSAJE GUARDADO NO ES EL DEL ARCHIVO.');
  console.error('  archivo:  %d caracteres', norm(mensaje).length);
  console.error('  guardado: %d caracteres', norm(guardado).length);
  const a = norm(mensaje), b = norm(guardado);
  let i = 0;
  while (i < Math.min(a.length, b.length) && a[i] === b[i]) i++;
  console.error('  primera diferencia en el caracter %d:', i);
  console.error('    archivo:  …%s', JSON.stringify(a.slice(i, i + 60)));
  console.error('    guardado: …%s', JSON.stringify(b.slice(i, i + 60)));
  console.error('');
  console.error('Revierto el commit y dejo los cambios en el índice.');
  git(['reset', '--soft', antes], { stdio: 'inherit' });
  process.exit(1);
}

console.log('mensaje verificado contra %s: %d caracteres, idénticos.',
            ruta, norm(mensaje).length);
