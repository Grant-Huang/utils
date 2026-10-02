// src/lib/renderers/xlsx.js
// XLSX renderer using xlsx-js-style, parameterised by Skill.

import XLSX from 'xlsx-js-style';

const headerStyle = (fill) => ({
  font: { name: '微软雅黑', sz: 11, bold: true, color: { rgb: 'FFFFFFFF' } },
  fill: { fgColor: { rgb: `FF${fill}` } },
  alignment: { horizontal: 'center', vertical: 'center', wrapText: true },
  border: {
    top: { style: 'thin', color: { rgb: 'FFB4C7E7' } },
    bottom: { style: 'thin', color: { rgb: 'FFB4C7E7' } },
    left: { style: 'thin', color: { rgb: 'FFB4C7E7' } },
    right: { style: 'thin', color: { rgb: 'FFB4C7E7' } },
  },
});

const dataStyle = {
  font: { name: '微软雅黑', sz: 10 },
  alignment: { horizontal: 'center', vertical: 'center' },
  border: {
    top: { style: 'thin', color: { rgb: 'FFB4C7E7' } },
    bottom: { style: 'thin', color: { rgb: 'FFB4C7E7' } },
    left: { style: 'thin', color: { rgb: 'FFB4C7E7' } },
    right: { style: 'thin', color: { rgb: 'FFB4C7E7' } },
  },
};

const numStyle = { ...dataStyle, font: { name: 'Consolas', sz: 10 }, alignment: { horizontal: 'right', vertical: 'center' } };
const leftStyle = { ...dataStyle, alignment: { horizontal: 'left', vertical: 'center', wrapText: true } };

function styleCell(sheet, addr, value, fill) {
  const isNum = typeof value === 'number';
  const isHeaderRow = addr.endsWith('1'); // simple heuristic; real logic below
  if (isHeaderRow) {
    sheet[addr].s = headerStyle(fill);
  } else if (addr.match(/A\d+$/) && !isNum) {
    sheet[addr].s = leftStyle;
  } else if (isNum) {
    sheet[addr].s = numStyle;
  } else {
    sheet[addr].s = dataStyle;
  }
}

export async function renderXlsx(doc, skill) {
  const wb = XLSX.utils.book_new();
  const sheets = doc.sheets ?? [];

  for (let si = 0; si < sheets.length; si++) {
    const sh = sheets[si];
    const sheet = XLSX.utils.aoa_to_sheet(sh.data);

    if (sh.cols) sheet['!cols'] = sh.cols.map(w => ({ wch: w }));
    if (sh.freeze !== false) sheet['!freeze'] = { xSplit: 0, ySplit: 1 };
    if (sh.autofilter) sheet['!autofilter'] = { ref: sh.autofilter };

    const fill = sh.headerFill ?? skill.theme.sheetHeaders[si % skill.theme.sheetHeaders.length];

    for (let r = 0; r < sh.data.length; r++) {
      for (let c = 0; c < sh.data[r].length; c++) {
        const addr = XLSX.utils.encode_cell({ r, c });
        if (!sheet[addr]) continue;
        if (r === 0) {
          sheet[addr].s = headerStyle(fill);
        } else if (c === 0) {
          sheet[addr].s = leftStyle;
        } else if (typeof sh.data[r][c] === 'number') {
          let style = numStyle;
          if (sh.condFormat?.column === c && typeof sh.condFormat.low === 'number' && sh.data[r][c] < sh.condFormat.low) {
            style = { ...numStyle, fill: { fgColor: { rgb: 'FFC6EFCE' } } };
          } else if (sh.condFormat?.column === c && typeof sh.condFormat.high === 'number' && sh.data[r][c] > sh.condFormat.high) {
            style = { ...numStyle, fill: { fgColor: { rgb: 'FFFFC7CE' } } };
          }
          sheet[addr].s = style;
        } else {
          sheet[addr].s = dataStyle;
        }
      }
    }

    XLSX.utils.book_append_sheet(wb, sheet, sh.name ?? `Sheet${si + 1}`);
  }

  // xlsx-js-style writes via write; returns Buffer in node
  return XLSX.write(wb, { type: 'buffer', bookType: 'xlsx' });
}
