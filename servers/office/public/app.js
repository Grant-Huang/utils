// public/app.js — demo front-end
const $ = (id) => document.getElementById(id);

const ASR = {
  meta: { creator: 'office-mcp demo', title: '2026 开源 ASR 横评' },
  cover: {
    title: '2026 年开源语音识别（ASR）方案横评报告',
    subtitle: '内部参考 · v1.0',
    fields: [['评测组', 'Hermes 评测组'], ['发布日期', '2026-10-02'], ['版本', 'v1.0']],
    abstract: '本报告以 2026 年 10 月时点的开源语音识别（ASR）生态为研究对象，从模型层、部署层、典型场景三个视角对主流开源方案做横向评测。',
  },
  toc: true,
  header: { text: '2026 开源 ASR 横评 · 内部参考' },
  footer: { text: '' },
  chapters: [
    {
      title: '第一章 模型层横评',
      level: 1,
      blocks: [
        { type: 'paragraph', text: '本章关注模型本身的静态属性与公开榜单表现。' },
        {
          type: 'table',
          caption: '表 1 主流开源 ASR 模型横向对比',
          widths: [1200, 1000, 700, 1000, 900, 800, 700, 800, 700],
          rows: [
            ['模型', '厂商/团队', '参数量', 'HF 下载量', '发布日期', '许可证', '典型 RTF', '中文 WER', '部署难度'],
            ['Qwen3-ASR-1.7B', 'Alibaba Qwen', '1.7B', '1,631,873', '2026-01-30', 'Apache-2.0', '0.08', '4.21', '中'],
            ['nemotron-3.5-asr-streaming-0.6b', 'NVIDIA', '0.6B', '1,191,490', '2026-09-10', 'CC-BY-4.0', '0.05', '6.78', '中'],
            ['VibeVoice-ASR', 'Microsoft', '7B', '727,707', '2026-01-27', 'MIT', '0.12', '4.95', '中高'],
            ['whisper-large-v3-turbo', 'OpenAI', '0.8B', '6,371,960', '2024-10-04', 'MIT', '0.06', '7.12', '低'],
          ],
        },
      ],
    },
    {
      title: '第二章 部署层横评',
      level: 1,
      blocks: [
        {
          type: 'table',
          caption: '表 2 五种部署形态对比',
          widths: [2200, 1600, 1800, 1700, 1500],
          rows: [
            ['部署形态', 'P50 延迟(s)', '吞吐', '显存/内存', '单小时成本(USD)'],
            ['端侧 (CoreML/GGUF)', '1.2', '0.6×', '2-3 GB RAM', '0.01'],
            ['服务端 CPU (Faster-Whisper int8)', '2.5', '4.0×', '8 GB RAM', '0.04'],
            ['服务端 GPU (A100 80G, vLLM)', '0.6', '18.0×', '24 GB VRAM', '0.12'],
          ],
        },
      ],
    },
    {
      title: '第三章 典型 ASR 推理流水线',
      level: 1,
      blocks: [
        { type: 'paragraph', text: '一个完整的 ASR 推理流水线通常包含 5 个阶段：音频输入 → VAD 分段 → 特征提取 → 模型推理 → 后处理。' },
        {
          type: 'flowchart',
          caption: '图 1 ASR 推理端到端流水线',
          nodes: [
            { label: '音频输入\nPCM 16kHz', color: '4472C4' },
            { label: 'VAD 分段\nSilero-VAD', color: 'ED7D31' },
            { label: '特征提取\nLog-Mel', color: '70AD47' },
            { label: '推理引擎\nTransformer', color: '7030A0' },
            { label: '后处理\nITN/Punct', color: 'C00000' },
          ],
        },
        {
          type: 'code',
          title: '样例：faster-whisper（CPU 服务端）',
          code: 'from faster_whisper import WhisperModel\nmodel = WhisperModel("large-v3", device="cpu", compute_type="int8")\nsegments, info = model.transcribe("audio.wav", beam_size=5)\nfor seg in segments:\n    print(f"[{seg.start:.2f}s -> {seg.end:.2f}s] {seg.text}")',
        },
      ],
    },
  ],
  references: [
    '[1] Radford A, et al. Robust Speech Recognition via Large-Scale Weak Supervision[C]//ICML. PMLR, 2023.',
    '[2] Qwen Team. Qwen3-ASR Technical Report[R]. Alibaba Group, 2026.',
    '[3] NVIDIA. Nemotron-3.5 Streaming ASR Model Card[R]. 2026.',
  ],
};

const ASR_SHEETS = {
  sheets: [
    {
      name: '模型对比',
      cols: [32, 16, 10, 14, 12, 12, 10, 10, 10],
      condFormat: { column: 7, low: 5, high: 7 },
      data: [
        ['模型', '厂商/团队', '参数量', 'HF 下载量', '发布日期', '许可证', '典型 RTF', '中文 WER', '部署难度'],
        ['Qwen3-ASR-1.7B', 'Alibaba Qwen', '1.7B', 1631873, '2026-01-30', 'Apache-2.0', 0.08, 4.21, '中'],
        ['nemotron-3.5-asr-streaming-0.6b', 'NVIDIA', '0.6B', 1191490, '2026-09-10', 'CC-BY-4.0', 0.05, 6.78, '中'],
        ['VibeVoice-ASR', 'Microsoft', '7B', 727707, '2026-01-27', 'MIT', 0.12, 4.95, '中高'],
        ['whisper-large-v3-turbo', 'OpenAI', '0.8B', 6371960, '2024-10-04', 'MIT', 0.06, 7.12, '低'],
      ],
    },
  ],
};

function buildPayload() {
  const fmt = $('fmt').value;
  let doc;
  if (fmt === 'xlsx') {
    doc = { ...ASR_SHEETS };
  } else if (fmt === 'pptx') {
    doc = {
      cover: { title: ASR.cover.title, subtitle: '内部参考 · v1.0 · Hermes 评测组' },
      chapters: ASR.chapters.map(ch => ({
        title: ch.title,
        level: ch.level,
        blocks: ch.blocks.map(b => {
          if (b.type === 'table') {
            return { type: 'table', headers: b.rows[0], rows: b.rows.slice(1) };
          }
          if (b.type === 'flowchart') return b;
          if (b.type === 'code') return { type: 'code', title: b.title, code: b.code };
          return b;
        }),
      })),
    };
  } else {
    doc = ASR;
  }

  const hex = (v) => v.replace('#', '').toUpperCase();
  const skill = {
    page: {
      margin: {
        top: Number($('marginTop').value),
        right: Number($('marginLeft').value),
        bottom: Number($('marginTop').value),
        left: Number($('marginLeft').value),
      },
    },
    body: { color: hex($('bodyColor').value) },
    table: { headerFill: hex($('tableHeaderFill').value) },
    code: { size: Number($('codeSize').value), borderColor: hex($('codeBorder').value) },
  };

  return { document: doc, skill, filename: `asr-report.${fmt}` };
}

function log(msg, cls = '') {
  const el = $('log');
  const line = document.createElement('div');
  line.className = cls;
  line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;   // textContent：避免错误文本被当作 HTML
  el.prepend(line);
}

// token 仅保存在本机浏览器 localStorage；不可用时（隐私模式等）退化为只在当前页面内存里
const TOKEN_KEY = 'office-mcp-token';
function loadToken() { try { return localStorage.getItem(TOKEN_KEY) || ''; } catch { return ''; } }
function saveToken(v) { try { localStorage.setItem(TOKEN_KEY, v); } catch {} }

async function checkHealth() {
  try {
    const r = await fetch('/health');
    const j = await r.json();
    $('health').textContent = `✓ ${j.formats.join('/')} · skill: ${j.skill}${j.auth ? ' · 需要 token' : ''}`;
    $('health').className = 'status ok';
  } catch (e) {
    $('health').textContent = '✗ 后端无响应 (run: npm start)';
    $('health').className = 'status err';
  }
}

async function generate() {
  const { document: doc, skill, filename } = buildPayload();
  const fmt = $('fmt').value;
  $('jsonOut').textContent = JSON.stringify({ document: doc, skill }, null, 2);
  log(`→ POST /render/${fmt}  (skill keys: ${Object.keys(skill).join(', ')})`);
  $('gen').disabled = true;
  try {
    const r = await fetch(`/render/${fmt}`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        ...($('token').value ? { authorization: `Bearer ${$('token').value}` } : {}),
      },
      body: JSON.stringify({ document: doc, skill, filename }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));
      log(r.status === 401 ? '✗ 未授权：请在右上角填写 Access token' : `✗ ${err.error}`, 'err');
      return;
    }
    const blob = await r.blob();
    const sizeKb = (blob.size / 1024).toFixed(1);
    try {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
      log(`✓ ${filename} (${sizeKb} KB) 下载触发`, 'ok');
    } catch (dlErr) {
      // sandboxed env (Playwright, headless) — fall back to data URL link
      const reader = new FileReader();
      reader.onload = () => {
        const a = document.createElement('a');
        a.href = reader.result; a.download = filename; a.click();
      };
      reader.readAsDataURL(blob);
      log(`✓ ${filename} (${sizeKb} KB) 通过 data URL 触发下载`, 'ok');
    }
  } catch (e) {
    log(`✗ ${e.message}`, 'err');
  } finally {
    $('gen').disabled = false;
  }
}

$('gen').addEventListener('click', generate);
$('json').addEventListener('click', () => {
  const { document, skill } = buildPayload();
  $('jsonOut').textContent = JSON.stringify({ document, skill }, null, 2);
  log('→ 已刷新 JSON 预览');
});
$('fmt').addEventListener('change', () => log(`格式切换为 ${$('fmt').value}`));

$('token').value = loadToken();
$('token').addEventListener('change', () => saveToken($('token').value));
checkHealth();
