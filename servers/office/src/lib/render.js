// src/lib/render.js — dispatch table
import { renderDocx } from './renderers/docx.js';
import { renderPptx } from './renderers/pptx.js';
import { renderXlsx } from './renderers/xlsx.js';
import { resolveSkill } from './skills/default.js';

export async function render(format, doc, skillOverrides = {}) {
  const skill = resolveSkill(skillOverrides);
  switch (format) {
    case 'docx': return await renderDocx(doc, skill);
    case 'pptx': return await renderPptx(doc, skill);
    case 'xlsx': return await renderXlsx(doc, skill);
    default: throw new Error(`unknown format: ${format}`);
  }
}

export function listFormats() {
  return ['docx', 'pptx', 'xlsx'];
}
