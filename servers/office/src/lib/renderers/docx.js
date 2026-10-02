// src/lib/renderers/docx.js
// DOCX renderer driven by Skill config + Document model JSON.
// Skill defaults live in src/lib/skills/default.js and reflect the
// best-practice values from BEST-PRACTICES-D.md (chapter 4, 7).

import {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType,
  PageBreak, Header, Footer, PageNumber,
} from 'docx';

// ---- helpers (mirror build_doc.js) --------------------------------------

const sz = (pt) => pt * 2; // docx uses half-points

const bodyRun = (text, base, opts = {}) =>
  new TextRun({
    text,
    size: sz(opts.size ?? base.body.size),
    bold: opts.bold ?? false,
    italics: opts.italics ?? false,
    color: opts.color ?? base.body.color,
    font: {
      ascii: opts.asciiFont ?? base.body.asciiFont,
      eastAsia: opts.eastAsiaFont ?? base.body.eastAsiaFont,
    },
    ...opts.extra,
  });

const heading = (text, level, base) =>
  new Paragraph({
    heading: HeadingLevel[`HEADING_${level}`],
    children: [new TextRun({
      text, bold: true,
      size: sz(base.heading[level].size),
      color: base.heading[level].color,
      font: {
        ascii: base.heading[level].asciiFont,
        eastAsia: base.heading[level].eastAsiaFont,
      },
    })],
  });

const para = (children, opts = {}) =>
  new Paragraph({
    children: Array.isArray(children) ? children : [children],
    alignment: opts.alignment,
    spacing: { line: opts.line, before: opts.before ?? 60, after: opts.after ?? 60, firstLine: opts.firstLine },
    ...opts.extra,
  });

// ---- table --------------------------------------------------------------

function shadedCell(text, base, opts) {
  return new TableCell({
    width: { size: opts.w, type: WidthType.DXA },
    shading: {
      type: ShadingType.CLEAR,
      fill: opts.fill ?? base.table.cellFill,
      color: 'auto',
    },
    children: [new Paragraph({
      alignment: opts.center ? AlignmentType.CENTER : AlignmentType.LEFT,
      children: [new TextRun({
        text: String(text ?? ''),
        bold: opts.bold ?? false,
        size: sz(opts.size ?? base.table.cellSize),
        color: opts.color ?? base.table.cellColor,
        font: {
          ascii: opts.asciiFont ?? base.table.asciiFont,
          eastAsia: opts.eastAsiaFont ?? base.table.eastAsiaFont,
        },
      })],
    })],
  });
}

function buildTable(tbl, base) {
  const widths = tbl.widths || tbl.rows[0].map(() => Math.floor(9000 / tbl.rows[0].length));
  // precedence: per-table > skill global > base default
  const headerFill = base.table.headerFill ?? tbl.headerFill ?? '4472C4';
  return new Table({
    columnWidths: widths,
    width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA },
    rows: tbl.rows.map((row, ri) => new TableRow({
      children: row.map((val, ci) => shadedCell(val, base, {
        w: widths[ci],
        bold: ri === 0,
        center: true,
        fill: ri === 0 ? headerFill : (tbl.altFill && ri % 2 === 0 ? tbl.altFill : base.table.cellFill ?? 'FFFFFF'),
        color: ri === 0 ? (base.table.headerColor ?? 'FFFFFF') : (base.table.cellColor ?? '000000'),
      })),
    })),
  });
}

// ---- flowchart (table-as-flow per BEST-PRACTICES-D §3) -------------------

function buildFlowchart(fc, base) {
  const n = fc.nodes.length;
  const nodeW = Math.floor(8000 / (n * 2 - 1));
  const arrowW = nodeW;
  const widths = [];
  for (let i = 0; i < n; i++) {
    widths.push(nodeW);
    if (i < n - 1) widths.push(arrowW);
  }
  const cells = [];
  fc.nodes.forEach((node, i) => {
    cells.push(shadedCell(node.label, base, {
      w: nodeW, fill: node.color, color: 'FFFFFF', bold: true, size: 10, center: true,
    }));
    if (i < n - 1) {
      cells.push(shadedCell('→', base, {
        w: arrowW, bold: true, size: 18, center: true,
      }));
    }
  });
  return new Table({
    columnWidths: widths,
    width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA },
    rows: [new TableRow({ children: cells })],
  });
}

// ---- code block ---------------------------------------------------------

function buildCodeBlock(cb, base) {
  // skill global overrides per-block borderColor (so a single skill config can retheme all code blocks)
  const borderColor = base.code.borderColor ?? cb.borderColor ?? '5B9BD5';
  const lines = cb.code.split('\n');
  return new Table({
    columnWidths: [base.code.width],
    width: { size: base.code.width, type: WidthType.DXA },
    rows: [new TableRow({
      children: [new TableCell({
        width: { size: base.code.width, type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: base.code.fill, color: 'auto' },
        borders: {
          top:    { style: BorderStyle.SINGLE, size: base.code.borderSize, color: borderColor },
          bottom: { style: BorderStyle.SINGLE, size: base.code.borderSize, color: borderColor },
          left:   { style: BorderStyle.SINGLE, size: base.code.borderSize, color: borderColor },
          right:  { style: BorderStyle.SINGLE, size: base.code.borderSize, color: borderColor },
        },
        children: lines.map(line => new Paragraph({
          children: [new TextRun({
            text: line,
            size: sz(base.code.size),
            font: { ascii: base.code.font, eastAsia: base.code.font },
            color: base.code.color,
          })],
          spacing: { before: 0, after: 0, line: 240 },
        })),
      })],
    })],
  });
}

// ---- header / footer (PAGE / NUMPAGES fields) ---------------------------

function buildHeader(text, base) {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [new TextRun({
      children: [
        `${text} · `,
        PageNumber.CURRENT,
        ' / ',
        PageNumber.TOTAL_PAGES,
      ],
      size: sz(base.header.size),
      color: base.header.color,
      font: { ascii: base.body.asciiFont, eastAsia: base.body.eastAsiaFont },
    })],
  });
}

function buildFooter(text, base) {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [new TextRun({
      text,
      size: sz(base.footer.size),
      font: { ascii: base.body.asciiFont, eastAsia: base.body.eastAsiaFont },
    })],
  });
}

// ---- main builder -------------------------------------------------------

export async function renderDocx(doc, skill) {
  const base = skill; // skill IS the style base in this version
  const children = [];

  // cover
  if (doc.cover) {
    children.push(new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 2400, after: 480 },
      children: [new TextRun({
        text: doc.cover.title,
        bold: true, size: sz(doc.cover.titleSize ?? 28),
        font: { ascii: base.body.asciiFont, eastAsia: '黑体' },
      })],
    }));
    if (doc.cover.subtitle) {
      children.push(new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 480 },
        children: [bodyRun(doc.cover.subtitle, base, { size: 16 })],
      }));
    }
    for (const [label, val] of doc.cover.fields ?? []) {
      children.push(new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [bodyRun(`${label}: ${val}`, base, { size: 14 })],
      }));
    }
    children.push(new Paragraph({ spacing: { before: 3600 }, children: [bodyRun('—— 摘要 ——', base, { size: 14, bold: true })] }));
    if (doc.cover.abstract) {
      children.push(new Paragraph({
        alignment: AlignmentType.JUSTIFY,
        spacing: { line: 360, firstLine: 440 },
        children: [bodyRun(doc.cover.abstract, base)],
      }));
    }
    children.push(new Paragraph({ children: [new PageBreak()] }));
  }

  // TOC placeholder (Word F9 refresh)
  if (doc.toc) {
    children.push(heading('目录', 1, base));
    children.push(new Paragraph({
      children: [bodyRun('【在 Word 中按 F9 刷新目录以生成实际页码】', base, { italics: true, color: '808080', size: 9 })],
    }));
    children.push(new Paragraph({ children: [new PageBreak()] }));
  }

  // chapters
  for (const ch of doc.chapters ?? []) {
    children.push(heading(ch.title, ch.level ?? 1, base));
    for (const block of ch.blocks ?? []) {
      if (block.type === 'paragraph') {
        children.push(para(bodyRun(block.text, base, block.opts ?? {}), block.para ?? {}));
      } else if (block.type === 'table') {
        children.push(buildTable(block, base));
        if (block.caption) {
          children.push(new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [bodyRun(block.caption, base, { italics: true, size: 9 })],
          }));
        }
      } else if (block.type === 'flowchart') {
        children.push(buildFlowchart(block, base));
        if (block.caption) {
          children.push(new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [bodyRun(block.caption, base, { italics: true, size: 9 })],
          }));
        }
      } else if (block.type === 'code') {
        if (block.title) {
          children.push(new Paragraph({
            children: [new TextRun({
              text: block.title, bold: true, size: sz(10),
              color: (block.borderColor ?? base.code.borderColor).replace('#', ''),
            })],
          }));
        }
        children.push(buildCodeBlock(block, base));
      } else if (block.type === 'pagebreak') {
        children.push(new Paragraph({ children: [new PageBreak()] }));
      }
    }
  }

  // references
  if (doc.references?.length) {
    children.push(new Paragraph({ children: [new PageBreak()] }));
    children.push(heading('参考文献', 1, base));
    for (const ref of doc.references) {
      children.push(para(bodyRun(ref, base), { spacing: { line: 280, before: 0, after: 30 } }));
    }
  }

  const document = new Document({
    creator: doc.meta?.creator ?? 'office-mcp',
    title: doc.meta?.title ?? 'Generated by office-mcp',
    styles: {
      default: {
        document: { run: { font: { ascii: base.body.asciiFont, eastAsia: base.body.eastAsiaFont }, size: sz(base.body.size) } },
      },
    },
    sections: [{
      properties: {
        page: {
          size: { width: base.page.width, height: base.page.height },
          margin: base.page.margin,
        },
      },
      headers: { default: new Header({ children: [buildHeader(doc.header?.text ?? '', base)] }) },
      footers: { default: new Footer({ children: [buildFooter(doc.footer?.text ?? '', base)] }) },
      children,
    }],
  });

  return await Packer.toBuffer(document);
}
