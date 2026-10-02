// src/lib/skills/default.js
// Default Skill: the values reflect BEST-PRACTICES-D.md chapters 4 + 7.
// All fields are overridable per-call via the Skill parameter.

export const defaultSkill = {
  name: 'office-d/v1',

  // Page geometry (DXA = twentieths of a point; 1 inch = 1440 DXA)
  page: {
    width: 11906,   // A4
    height: 16838,  // A4
    margin: { top: 1440, right: 1797, bottom: 1440, left: 1797 },
  },

  body: {
    asciiFont: 'Times New Roman',
    eastAsiaFont: '宋体',
    size: 11,
    color: '000000',
  },

  heading: {
    1: { size: 16, color: '1F4E79', asciiFont: 'Times New Roman', eastAsiaFont: '黑体' },
    2: { size: 14, color: '2E75B6', asciiFont: 'Times New Roman', eastAsiaFont: '黑体' },
    3: { size: 12, color: '2E75B6', asciiFont: 'Times New Roman', eastAsiaFont: '黑体' },
  },

  table: {
    headerFill: '4472C4',
    headerColor: 'FFFFFF',
    cellFill: 'FFFFFF',
    cellColor: '000000',
    cellSize: 9,
    asciiFont: 'Times New Roman',
    eastAsiaFont: '黑体',
  },

  code: {
    fill: 'F2F2F2',
    color: '1A1A1A',
    size: 9,
    font: 'Courier New',
    borderColor: '5B9BD5',
    borderSize: 8,
    width: 8500,
  },

  header: { size: 9, color: '808080' },
  footer: { size: 9, color: '000000' },

  theme: {
    primary: '1F4E79',
    sheetHeaders: ['FF1F4E79', 'FF70AD47', 'FF7030A0', 'FFED7D31', 'FFC00000'],
  },

  font: {
    cnBody: '微软雅黑',
    cnHeading: '微软雅黑',
    code: 'Courier New',
  },
};

// Resolve user overrides onto defaults without losing nested values.
export function resolveSkill(overrides = {}) {
  const out = JSON.parse(JSON.stringify(defaultSkill));
  for (const k of Object.keys(overrides)) {
    const v = overrides[k];
    if (v && typeof v === 'object' && !Array.isArray(v) && out[k] && typeof out[k] === 'object') {
      out[k] = { ...out[k], ...v };
    } else if (v !== undefined) {
      out[k] = v;
    }
  }
  return out;
}
