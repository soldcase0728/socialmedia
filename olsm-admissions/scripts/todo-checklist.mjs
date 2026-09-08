#!/usr/bin/env node
/**
 * Prints every "TODO: confirm" in the source, grouped by the page it appears on,
 * so the school can fill in facts without reading code.
 *
 *   npm run todos            # grouped checklist
 *   npm run todos -- --md    # same, as Markdown to paste into a doc
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const ROOT = new URL('..', import.meta.url).pathname.replace(/\/$/, '');
const SKIP = new Set(['node_modules', 'dist', '.astro', '.vercel', '.git', 'scripts']);
const SKIP_FILES = new Set(['README.md']);
const EXT = /\.(astro|md|mdx|ts|tsx|js|mjs|css|json)$/;
const MARKER = /TODO:\s*confirm\s*(?:—|--|-|:)?\s*(.*)$/i;

/** Which URL a source file is responsible for. */
function pageFor(file) {
  const p = relative(ROOT, file);
  if (p.startsWith('src/content/pages/')) return '/' + p.replace('src/content/pages/', '').replace(/\.mdx?$/, '');
  if (p === 'src/pages/index.astro') return '/';
  if (p.startsWith('src/pages/api/')) return '(form endpoints)';
  if (p.startsWith('src/pages/')) return '/' + p.replace('src/pages/', '').replace(/\.(astro|ts)$/, '');
  if (p.startsWith('src/config/')) return '(site config — affects every page)';
  if (p.startsWith('src/components/') || p.startsWith('src/layouts/')) return '(shared components)';
  return '(other)';
}

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (SKIP.has(name) || name.startsWith('.')) continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (EXT.test(name) && !SKIP_FILES.has(name)) out.push(full);
  }
  return out;
}

const groups = new Map();
let total = 0;

for (const file of walk(ROOT)) {
  const lines = readFileSync(file, 'utf8').split('\n');
  lines.forEach((line, i) => {
    const m = line.match(MARKER);
    if (!m) return;
    // A marker used as a placeholder *value* ('TODO: confirm') carries no
    // question; report the field it sits in instead of the rest of the line.
    const inQuotes = /['"`]TODO:\s*confirm['"`]/i.test(line);
    let question = inQuotes
      ? `value for: ${line.trim().replace(/\s+/g, ' ').slice(0, 110)}`
      : (m[1] || '')
          .replace(/(-->|\*\/|<\/[a-z]+>)\s*$/gi, '')
          .replace(/&mdash;|&amp;/g, '')
          .replace(/^\W+/, '')
          .trim();
    if (!question) question = '(no detail given — read the line in context)';

    const page = pageFor(file);
    if (!groups.has(page)) groups.set(page, []);
    const bucket = groups.get(page);
    // An HTML-comment marker followed within two lines by the visible copy is
    // one fact, not two. Keep whichever wording is longer.
    const prev = bucket[bucket.length - 1];
    const prevLine = prev ? Number(prev.where.split(':').pop()) : -99;
    const sameFile = prev && prev.where.startsWith(relative(ROOT, file) + ':');
    if (sameFile && i + 1 - prevLine <= 2) {
      if (question.length > prev.question.length) prev.question = question;
      return;
    }
    bucket.push({ question, where: `${relative(ROOT, file)}:${i + 1}` });
    total += 1;
  });
}

const md = process.argv.includes('--md');
const ordered = [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));

if (md) {
  console.log(`# Facts to confirm\n\n${total} items across ${ordered.length} pages.\n`);
  for (const [page, items] of ordered) {
    console.log(`## ${page}\n`);
    for (const it of items) console.log(`- [ ] ${it.question}  \n      \`${it.where}\``);
    console.log('');
  }
} else {
  console.log(`\nFacts to confirm: ${total} across ${ordered.length} pages\n`);
  for (const [page, items] of ordered) {
    console.log(`${page}  (${items.length})`);
    for (const it of items) console.log(`  [ ] ${it.question}\n      ${it.where}`);
    console.log('');
  }
}
