/* utils 集市前端：无框架、hash 路由。数据来自 data/catalog.json（由 site/build.py 生成）。
 * 安全：来自数据的文本一律用 textContent 写入；只有构建时已转义原始 HTML 的 Markdown 才用 innerHTML。 */
(() => {
  'use strict';
  const app = document.getElementById('app');
  const baseInput = document.getElementById('base-url');
  let CAT = null;

  // ---------- 小工具 ----------
  const store = (area) => ({
    get(k) { try { return window[area].getItem(k); } catch { return null; } },
    set(k, v) { try { window[area].setItem(k, v); } catch { /* 隐私模式等：忽略，页面仍可用 */ } },
  });
  const local = store('localStorage'), sess = store('sessionStorage');

  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    return el;
  }
  const mdBox = (html) => { const d = h('div', { class: 'prose' }); d.innerHTML = html; return d; };
  const fmtTime = (iso) => iso ? iso.replace('T', ' ').replace('Z', ' UTC') : '';
  const pretty = (v) => typeof v === 'string' ? v : JSON.stringify(v, null, 2);

  function copyBtn(text) {
    const b = h('button', { class: 'copy', type: 'button', text: '复制' });
    b.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(text); b.textContent = '已复制'; }
      catch {
        const ta = h('textarea', { style: 'position:fixed;opacity:0' }); ta.value = text; document.body.append(ta); ta.select();
        try { document.execCommand('copy'); b.textContent = '已复制'; } catch { b.textContent = '请手动复制'; }
        ta.remove();
      }
      setTimeout(() => (b.textContent = '复制'), 1500);
    });
    return b;
  }
  const snip = (text) => h('div', { class: 'snip' }, copyBtn(text), h('pre', {}, h('code', { text })));

  function getBase() {
    const v = (baseInput.value || '').trim().replace(/\/+$/, '');
    if (v) return v;
    if (CAT.config.baseUrl) return CAT.config.baseUrl.replace(/\/+$/, '');
    return location.protocol.startsWith('http') ? location.origin : CAT.config.exampleBaseUrl;
  }
  const catLabel = (type, key) => (CAT.taxonomy[type].find((c) => c.key === key) || {}).label || key;
  const riskInfo = (key) => CAT.taxonomy.risk.find((r) => r.key === key) || { label: key, hint: '' };
  const byId = (id) => CAT.items.find((i) => i.id === id);
  const route = (item) => `#/${item.type === 'mcp' ? 'mcp' : 'skills'}/${item.id}`;
  const tokenEnv = (item) => (item.tokenScope === 'browser' ? 'UTILS_BROWSER_TOKEN' : 'UTILS_MCP_TOKEN');

  function badges(item) {
    const out = [];
    if (item.type === 'mcp') {
      out.push(h('span', { class: 'badge', text: item.origin === 'self' ? '自研' : '第三方' }));
      const r = riskInfo(item.risk);
      out.push(h('span', { class: `badge ${item.risk}`, title: r.hint, text: r.label }));
      if (item.tokenScope === 'browser') out.push(h('span', { class: 'badge bad', text: '专用 token' }));
      if (item.live) out.push(h('span', { class: 'badge live', text: '可实际调用' }));
    } else {
      out.push(h('span', { class: 'badge', text: `依赖 ${item.dependsOn.length} 个 MCP` }));
    }
    if (item.recordings.length) out.push(h('span', { class: 'badge rec', text: `${item.recordings.length} 份录制` }));
    return h('div', { class: 'badges' }, out);
  }

  // ---------- 路由 ----------
  function parse() {
    const parts = (location.hash.replace(/^#\/?/, '') || '').split('/').filter(Boolean).map(decodeURIComponent);
    return { section: parts[0] || 'home', id: parts[1], tab: parts[2] };
  }
  function render() {
    if (!CAT) return;
    const r = parse();
    document.querySelectorAll('[data-nav]').forEach((a) => a.classList.toggle('on', a.dataset.nav === r.section));
    app.replaceChildren();
    if (r.section === 'mcp' || r.section === 'skills') {
      const type = r.section === 'mcp' ? 'mcp' : 'skill';
      if (!r.id) return app.append(listView(type));
      const item = byId(r.id);
      if (!item || item.type !== type) return app.append(notFound());
      document.title = `${item.title} · ${CAT.config.title}`;
      return app.append(detailView(item, r.tab));
    }
    document.title = CAT.config.title;
    app.append(homeView());
  }
  const notFound = () => h('div', { class: 'empty' }, '没有找到这个页面。', h('a', { href: '#/', text: ' 回到首页' }));

  // ---------- 首页 ----------
  function homeView() {
    const n = (t) => CAT.items.filter((i) => i.type === t).length;
    const skills = CAT.items.filter((i) => i.type === 'skill');
    return h('div', {},
      h('h1', { text: CAT.config.title }),
      h('p', { class: 'sub', text: CAT.config.subtitle }),
      h('div', { class: 'hero-grid' },
        h('a', { class: 'tile', href: '#/mcp' }, h('div', { class: 'n', text: n('mcp') }), h('strong', { text: 'MCP 集市' }), h('div', { class: 'meta', text: '连接服务的能力：文档生成、读取、数据分析、联网……' })),
        h('a', { class: 'tile', href: '#/skills' }, h('div', { class: 'n', text: n('skill') }), h('strong', { text: 'Skill 集市' }), h('div', { class: 'meta', text: '教模型怎么用这些能力完成一类任务' }))),
      h('h2', { text: '它们是什么关系' }),
      h('div', { class: 'panel' }, h('p', {}, 'MCP 提供能力（工具），Skill 提供做法（说明书）。Skill 本身不发请求，是模型读了 Skill 再去调用 MCP。安装 Skill 时，它依赖的 MCP 会一起安装。')),
      h('h2', { text: '外部服务怎么用' }),
      h('div', { class: 'panel' },
        h('p', {}, h('strong', { text: 'MCP：' }), '用服务地址 + Bearer token 直接调用（每个项目的“调用说明”页有 curl、Python、通用 JSON 示例）。'),
        h('p', {}, h('strong', { text: 'Skill：' }), '在项目页下载 Skill 包，放进你们服务的 ', h('code', { text: '.claude/skills/' }), '，并配好它依赖的 MCP。'),
        h('p', { class: 'meta', text: 'token 由管理员在服务端发放，建议每个调用方一个，吊销时删掉即可。' })),
      h('h2', { text: '推荐组合（装一个 Skill，自动带上它依赖的 MCP）' }),
      h('div', { class: 'cards' }, skills.map((s) => h('a', { class: 'card', href: route(s) },
        h('h3', { text: s.title }), h('p', { text: s.summary }),
        h('div', { class: 'meta', text: '依赖：' + (s.dependsOn.map((d) => (byId(d) || {}).title || d).join('、') || '无') })))));
  }

  // ---------- 列表 ----------
  const listState = { mcp: { cat: 'all', q: '', risk: 'all', demo: false }, skill: { cat: 'all', q: '', demo: false } };
  function listView(type) {
    const st = listState[type];
    const all = CAT.items.filter((i) => i.type === type);
    const wrap = h('div', {});
    const title = type === 'mcp' ? 'MCP 集市' : 'Skill 集市';
    wrap.append(h('h1', { text: title }), h('p', { class: 'sub', text: type === 'mcp' ? '每个 MCP 是一个已部署的服务，带地址、token 和风险说明。' : '每个 Skill 是一份给模型的工作流说明，依赖若干 MCP。' }));
    const tabs = h('div', { class: 'tabs', role: 'tablist' });
    const cards = h('div', { class: 'cards' });
    const redraw = () => {
      tabs.replaceChildren();
      const cats = CAT.taxonomy[type].filter((c) => all.some((i) => i.category === c.key));
      for (const c of [{ key: 'all', label: '全部' }, ...cats]) {
        tabs.append(h('button', { class: 'tab' + (st.cat === c.key ? ' on' : ''), role: 'tab', type: 'button', 'data-cat': c.key,
          onclick: () => { st.cat = c.key; redraw(); } }, `${c.label}${c.key === 'all' ? ` (${all.length})` : ` (${all.filter((i) => i.category === c.key).length})`}`));
      }
      const q = st.q.trim().toLowerCase();
      const shown = all.filter((i) => (st.cat === 'all' || i.category === st.cat)
        && (type !== 'mcp' || st.risk === 'all' || i.risk === st.risk)
        && (!st.demo || i.hasDemo)
        && (!q || [i.title, i.summary, i.id, ...(i.tags || [])].join(' ').toLowerCase().includes(q)));
      cards.replaceChildren(...(shown.length ? shown.map((i) => h('a', { class: 'card', href: route(i), 'data-id': i.id },
        h('h3', { text: i.title }), h('p', { text: i.summary }), badges(i))) : [h('div', { class: 'empty', text: '没有符合条件的项目。' })]));
    };
    const search = h('input', { type: 'search', placeholder: '搜索名称、简介、标签', value: st.q, 'aria-label': '搜索', oninput: (e) => { st.q = e.target.value; redraw(); } });
    const tools = h('div', { class: 'tools' }, search);
    if (type === 'mcp') {
      const sel = h('select', { 'aria-label': '风险等级', onchange: (e) => { st.risk = e.target.value; redraw(); } },
        h('option', { value: 'all', text: '全部风险等级' }), CAT.taxonomy.risk.map((r) => h('option', { value: r.key, text: r.label })));
      sel.value = st.risk; tools.append(sel);
    }
    tools.append(h('label', {}, h('input', { type: 'checkbox', checked: st.demo || null, onchange: (e) => { st.demo = e.target.checked; redraw(); } }), ' 只看有 demo 的'));
    wrap.append(tools, tabs, cards);
    redraw();
    return wrap;
  }

  // ---------- 详情 ----------
  function detailView(item, tab) {
    const tabs = [['detail', '详情'], ['usage', '调用说明']];
    if (item.hasDemo) tabs.push(['demo', 'Demo']);
    const cur = tabs.some((t) => t[0] === tab) ? tab : 'detail';       // 没有 demo 的项目访问 /demo 时回到详情
    const back = item.type === 'mcp' ? ['#/mcp', 'MCP 集市'] : ['#/skills', 'Skill 集市'];
    const body = h('div', { 'data-tab': cur });
    if (cur === 'detail') body.append(item.type === 'mcp' ? mcpDetail(item) : skillDetail(item));
    else if (cur === 'usage') body.append(item.type === 'mcp' ? mcpUsage(item) : skillUsage(item));
    else body.append(demoView(item));
    return h('div', {},
      h('div', { class: 'crumb' }, h('a', { href: back[0], text: back[1] }), ' / ', item.title),
      h('div', { class: 'head' }, h('div', { class: 'grow' }, h('h1', { text: item.title }), h('p', { class: 'sub', text: item.summary }), badges(item)),
        h('div', { class: 'meta', text: `${item.id} · v${item.version}` })),
      h('div', { class: 'tabs', role: 'tablist' }, tabs.map(([k, label]) => h('a', { class: k === cur ? 'on' : '', role: 'tab', 'data-tab-link': k, href: `${route(item)}/${k}`, text: label }))),
      body);
  }

  function paramRows(schema) {
    const props = (schema && schema.properties) || {};
    const req = new Set((schema && schema.required) || []);
    const typeOf = (p) => p.type || (p.anyOf ? p.anyOf.map((x) => x.type).filter(Boolean).join(' | ') : '') || '';
    const rows = Object.entries(props).map(([k, p]) => h('tr', {}, h('td', {}, h('code', { text: k }), req.has(k) ? h('span', { class: 'req', text: ' *' }) : null), h('td', { text: typeOf(p) }), h('td', { text: (p.description || '').slice(0, 300) })));
    if (!rows.length) return h('div', { class: 'meta', text: '无参数' });
    return h('table', { class: 'tbl' }, h('thead', {}, h('tr', {}, h('th', { text: '参数' }), h('th', { text: '类型' }), h('th', { text: '说明' }))), h('tbody', {}, rows));
  }

  function mcpDetail(item) {
    const r = riskInfo(item.risk);
    const out = h('div', {});
    out.append(h('div', { class: `note ${item.risk === 'low' ? 'ok' : item.risk === 'high' ? 'bad' : ''}` }, h('strong', { text: `${r.label}：` }), item.riskNote));
    if (item.upstream) {
      out.append(h('p', { class: 'meta' }, '上游：', h('a', { href: item.upstream.url, target: '_blank', rel: 'noopener noreferrer', text: item.upstream.name }),
        ` · 我们钉死的版本 ${item.upstream.version} · license：${item.upstream.license}`));
    }
    out.append(mdBox(item.detailHtml));
    const tools = item.tools || [];
    out.append(h('h2', { text: `工具清单（${tools.length}）` }));
    const list = h('div', { class: 'panel' });
    for (const t of tools) {
      list.append(h('details', { class: 'tool-item' }, h('summary', {}, h('span', { class: 'nm', text: t.name }), t.title ? ` · ${t.title}` : ''),
        h('p', { text: (t.description || '').trim() }), paramRows(t.inputSchema)));
    }
    out.append(list);
    if (item.snapshot) {
      const s = item.snapshot.server || {};
      out.append(h('p', { class: 'meta', text: `工具清单来自真实服务的快照（${fmtTime(item.snapshot.at)}）。服务自报：${s.name || '?'} ${s.version || ''}；第三方服务自报的版本不一定准确，以上面钉死的版本为准。` }));
    }
    if (item.usedBy.length) out.append(h('h2', { text: '被这些 Skill 使用' }), h('div', { class: 'chips' }, item.usedBy.map((id) => h('a', { class: 'chip', href: route(byId(id)), text: byId(id).title }))));
    return out;
  }

  function skillDetail(item) {
    const out = h('div', {});
    out.append(mdBox(item.detailHtml));
    out.append(h('h2', { text: '依赖的 MCP' }));
    out.append(h('div', { class: 'chips' }, item.dependsOn.map((id) => { const d = byId(id); return d ? h('a', { class: 'chip', href: route(d) }, d.title, ' ', h('span', { class: `badge ${d.risk}`, text: riskInfo(d.risk).label })) : h('span', { class: 'chip', text: id }); })));
    out.append(h('h2', { text: '模型靠什么决定触发它' }), h('p', { class: 'meta', text: '下面是 Skill 的 description，模型据此判断是否使用：' }), h('pre', {}, item.skillDescription));
    out.append(h('details', {}, h('summary', { text: '查看 SKILL.md 源文件' }), h('pre', {}, h('code', { text: item.skillSource }))));
    return out;
  }

  // ---------- 调用说明 ----------
  function mcpUsage(item) {
    const base = getBase(), url = base + item.endpoint, env = tokenEnv(item), call = item.examples.calls[0];
    const out = h('div', {});
    out.append(h('h2', { text: '1. 先拿到 token' }),
      h('div', { class: 'panel' },
        h('p', {}, '向管理员申请 token（服务端的 ', h('code', { text: 'MCP_AUTH_TOKENS' }), item.tokenScope === 'browser' ? ' 之外，另有专用的 MCP_BROWSER_TOKENS' : '', '）。调用时放在请求头 ', h('code', { text: 'Authorization: Bearer <token>' }), '。'),
        item.tokenScope === 'browser' ? h('div', { class: 'note bad', text: '这是高权限的专用通道：普通 token 不能用，只发给确实需要的人。' }) : null,
        h('p', { class: 'meta', text: '建议每个调用方一个独立 token，吊销只需在服务端删掉对应项。token 只放环境变量或密钥管理，不要写进代码、镜像或仓库。' })));

    const kinds = {
      'Claude Code 插件': `export UTILS_MCP_URL=${base}\nexport ${env}=<你的 token>\nclaude plugin marketplace add ${CAT.config.repo}\nclaude plugin install ${item.id}@${CAT.config.marketplaceName}\nclaude mcp list        # 应显示 plugin:${item.id}:${item.serverName} … Connected`,
      'claude mcp add': `claude mcp add --transport http ${item.serverName} ${url} \\\n  --header "Authorization: Bearer $${env}"`,
      '通用 JSON': JSON.stringify({ mcpServers: { [item.serverName]: { type: 'http', url, headers: { Authorization: `Bearer \${${env}}` } } } }, null, 2),
      'curl': `curl -s ${url} \\\n  -H "Authorization: Bearer $${env}" \\\n  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \\\n  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'`
        + (item.id === 'mcp-browser' ? '\n# browser 是有状态服务：先 initialize，再把响应头里的 Mcp-Session-Id 带在后续请求里' : ''),
      'Python（服务端）': CAT.snippets.python.replace('{{URL}}', url).replace('{{TOKEN_ENV}}', env).replace('{{TOOL}}', call.tool).replace('{{ARGS_JSON}}', JSON.stringify(call.arguments, null, 2).replace(/\n/g, '\n' + ' '.repeat(26))),
    };
    out.append(h('h2', { text: '2. 接入' }));
    const holder = h('div', {}), tabBar = h('div', { class: 'tabs' });
    const show = (k) => { holder.replaceChildren(snip(kinds[k])); tabBar.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.textContent === k)); };
    for (const k of Object.keys(kinds)) tabBar.append(h('button', { class: 'tab', type: 'button', text: k, onclick: () => show(k) }));
    out.append(tabBar, holder); show('Claude Code 插件');

    out.append(h('h2', { text: '3. 外部服务调用' }), h('div', { class: 'panel' },
      h('p', {}, '你们自己部署的服务和上面是同一种调用：向 ', h('code', { text: url }), ' 发 HTTP POST，带 Bearer token，按 MCP 的 JSON-RPC 格式发 ', h('code', { text: 'initialize' }), ' → ', h('code', { text: 'tools/call' }), '。上面的 “Python（服务端）” 只用标准库，可以直接改。'),
      h('p', { class: 'meta', text: '部分服务按 token 限流，具体额度由管理员配置。' })));

    out.append(h('h2', { text: '4. 示例调用' }));
    const recTools = new Set(item.recordings.flatMap((r) => r.steps.filter((s) => s.type === 'tool_call').map((s) => s.tool)));
    for (const c of item.examples.calls) {
      out.append(h('div', { class: 'panel' }, h('strong', { text: c.title }), ' ', h('code', { text: c.tool }),
        recTools.has(c.tool) ? h('span', { class: 'badge rec', text: '有录制' }) : h('span', { class: 'badge', text: '参数已按 schema 校验' }), snip(JSON.stringify(c.arguments, null, 2))));
    }
    out.append(h('h2', { text: '5. 排错' }), h('table', { class: 'tbl' }, h('thead', {}, h('tr', {}, h('th', { text: '现象' }), h('th', { text: '原因' }))), h('tbody', {},
      [['Missing environment variables: UTILS_MCP_URL', '环境变量没设置（插件方式）'],
       ['HTTP 401 / Server rejected the configured Authorization header', 'token 不对，或用了不属于该通道的 token'],
       ['HTTP 403 / 421 Invalid Host', 'Host 或 Origin 不在服务端白名单里'],
       ['HTTP 429', '触发了限流'],
       ['ECONNREFUSED', '地址不通或服务没起来'],
       ['结果里 isError: true', '工具执行失败，文本里有原因，按原因修正参数后重试']].map(([a, b]) => h('tr', {}, h('td', {}, h('code', { text: a })), h('td', { text: b }))))));
    if (item.usageExtraHtml) out.append(mdBox(item.usageExtraHtml));
    return out;
  }

  function skillUsage(item) {
    const base = getBase(), out = h('div', {});
    out.append(h('h2', { text: '1. 在 Claude Code 里安装' }), snip(`claude plugin marketplace add ${CAT.config.repo}\nclaude plugin install ${item.id}@${CAT.config.marketplaceName}     # 会自动带上依赖的 MCP 插件`),
      h('p', { class: 'meta', text: '依赖的 MCP 需要环境变量 UTILS_MCP_URL 和 UTILS_MCP_TOKEN（浏览器通道另需 UTILS_BROWSER_TOKEN）。' }));

    out.append(h('h2', { text: '2. 部署到你们自己的服务里（下载）' }));
    const dl = item.downloads || {};
    const files = h('div', { class: 'panel' });
    if (dl.skill) files.append(h('p', {}, h('a', { href: dl.skill.file, download: '', text: 'Skill 包（.zip）' }), h('span', { class: 'meta', text: ` ${(dl.skill.bytes / 1024).toFixed(1)} KB · sha256 ${dl.skill.sha256.slice(0, 12)}…` }),
      h('br'), '解压到服务的 ', h('code', { text: `.claude/skills/` }), '，得到 ', h('code', { text: `.claude/skills/${item.skillName}/SKILL.md` }), '。'));
    if (dl.plugin) files.append(h('p', {}, h('a', { href: dl.plugin.file, download: '', text: '完整插件包（.zip）' }), h('span', { class: 'meta', text: ` ${(dl.plugin.bytes / 1024).toFixed(1)} KB` }),
      h('br'), '或用 ', h('code', { text: `claude --plugin-dir ./${item.id}-plugin.zip` }), ' 加载。'));
    if (!dl.skill) files.append(h('p', { class: 'meta', text: '当前页面不是由完整构建生成，没有下载包。' }));
    out.append(files);
    out.append(h('p', {}, '部署后还需要让你们的服务能连上它依赖的 MCP。每个依赖的连接配置如下（token 放环境变量）：'));
    for (const id of item.dependsOn) {
      const d = byId(id); if (!d) continue;
      const cfg = JSON.stringify({ mcpServers: { [d.serverName]: { type: 'http', url: base + d.endpoint, headers: { Authorization: `Bearer \${${tokenEnv(d)}}` } } } }, null, 2);
      out.append(h('div', { class: 'panel' }, h('strong', { text: d.title }), ' ', h('a', { href: `${route(d)}/usage`, text: '（调用说明）' }), d.tokenScope === 'browser' ? h('span', { class: 'badge bad', text: '专用 token' }) : null, snip(cfg)));
    }

    out.append(h('h2', { text: '3. 怎么触发' }), h('p', { class: 'meta', text: '直接像下面这样提问。是否触发取决于模型对 Skill description 的判断，详见“详情”页的验证状态。' }));
    for (const p of item.examples.prompts) out.append(h('div', { class: 'panel' }, snip(p)));
    if (item.usageExtraHtml) out.append(mdBox(item.usageExtraHtml));
    return out;
  }

  // ---------- Demo ----------
  function demoView(item) {
    const out = h('div', {});
    const panes = [];
    if (item.recordings.length) panes.push(['replay', '录制回放', () => replayPane(item)]);
    if (item.live) panes.push(['live', '实际调用', () => livePane(item)]);
    const bar = h('div', { class: 'tabs', role: 'tablist' }), box = h('div', {});
    const show = (key) => { const p = panes.find((x) => x[0] === key); box.replaceChildren(p[2]()); bar.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.pane === key)); };
    for (const [k, label] of panes) bar.append(h('button', { class: 'tab', type: 'button', role: 'tab', 'data-pane': k, text: label, onclick: () => show(k) }));
    out.append(bar, box); show(panes[0][0]);
    return out;
  }

  function contentNodes(content) {
    return (content || []).map((c) => {
      if (c.type === 'text') return h('pre', {}, h('code', { text: c.text }));
      if (c.type === 'resource_link') return h('div', {}, '资源链接：', h('code', { text: c.uri }), c.mimeType ? h('span', { class: 'meta', text: `  ${c.mimeType}` }) : null);
      if (c.type === 'resource') return h('div', { class: 'meta', text: `内嵌资源 ${c.mimeType || ''}${c.bytes ? ` · 约 ${c.bytes} 字节` : ''}` });
      return h('pre', {}, h('code', { text: pretty(c) }));
    });
  }

  function stepNode(s) {
    const trunc = s.truncated ? h('div', { class: 'trunc', text: '⚠ 内容过长，已被截断（标注了原长度和 sha256）' }) : null;
    if (s.type === 'user') return h('div', { class: 'step user' }, h('div', { class: 'who', text: '用户' }), h('div', { text: s.text, style: 'white-space:pre-wrap;word-break:break-word' }), trunc);
    if (s.type === 'assistant') return h('div', { class: 'step assistant' }, h('div', { class: 'who', text: '模型' }), h('div', { text: s.text, style: 'white-space:pre-wrap' }));
    if (s.type === 'tool_call') return h('div', { class: 'step tool_call' }, h('div', { class: 'who' }, '调用 ', h('code', { text: s.tool })), h('pre', {}, h('code', { text: pretty(s.arguments) })), trunc);
    return h('div', { class: `step tool_result ${s.isError ? 'err' : 'ok'}` }, h('div', { class: 'who', text: `${s.isError ? '返回（出错 isError）' : '返回'}${s.durationMs != null ? ` · ${s.durationMs} ms` : ''}` }), contentNodes(s.content), trunc);
  }

  function replayPane(item) {
    const out = h('div', {});
    const holder = h('div', {});
    const draw = (rec) => {
      holder.replaceChildren();
      const steps = h('div', { class: 'steps' }, rec.steps.map(stepNode));
      let timer = null;
      const stop = () => { clearInterval(timer); timer = null; play.textContent = '▶ 回放'; };
      const play = h('button', { type: 'button', class: 'primary', text: '▶ 回放', onclick: () => {
        if (timer) return stop();
        const nodes = [...steps.children]; nodes.forEach((n) => (n.hidden = true)); let i = 0; play.textContent = '■ 停止';
        timer = setInterval(() => { if (i < nodes.length) nodes[i++].hidden = false; else stop(); }, 900);
      } });
      const all = h('button', { type: 'button', text: '全部显示', onclick: () => { stop(); [...steps.children].forEach((n) => (n.hidden = false)); } });
      const st = rec.stats || {};
      const meta = [`录制于 ${fmtTime(rec.recordedAt)}`, st.model ? `模型 ${st.model}` : null, st.costUsd != null ? `花费 $${Number(st.costUsd).toFixed(3)}` : null, st.durationMs != null ? `耗时 ${(st.durationMs / 1000).toFixed(1)} s` : null].filter(Boolean).join(' · ');
      holder.append(h('div', { class: 'note ok', text: rec.kind === 'skill' ? '这是一次真实的模型会话录制（不是手写的脚本），包括模型是否调用了 Skill。' : '这是对真实服务的一次真实调用，返回内容原样记录。' }),
        rec.description ? h('p', { text: rec.description }) : null, h('div', { class: 'replay-bar' }, play, all, h('span', { class: 'meta', text: meta })),
        (rec.normalized || []).length ? h('div', { class: 'meta', text: `展示时的规范化：${rec.normalized.join('；')}` }) : null, steps);
    };
    if (item.recordings.length > 1) {
      const sel = h('select', { 'aria-label': '选择录制', onchange: (e) => draw(item.recordings[+e.target.value]) }, item.recordings.map((r, i) => h('option', { value: i, text: r.title })));
      out.append(h('div', { class: 'tools' }, '选择录制：', sel));
    } else out.append(h('h3', { text: item.recordings[0].title }));
    out.append(holder); draw(item.recordings[0]);
    return out;
  }

  // 实际调用：浏览器直接对服务发 MCP（initialize → tools/call），用访问者自己的 token
  async function mcpCall(url, token, tool, args) {
    const headers = { 'content-type': 'application/json', accept: 'application/json, text/event-stream', authorization: `Bearer ${token}` };
    const post = async (payload) => {
      const r = await fetch(url, { method: 'POST', headers, body: JSON.stringify(payload) });
      if (r.headers.get('mcp-session-id')) headers['mcp-session-id'] = r.headers.get('mcp-session-id');
      const text = await r.text();
      if (!r.ok) throw new Error(`HTTP ${r.status}：${text.slice(0, 200)}`);
      if (!text.trim()) return {};
      if ((r.headers.get('content-type') || '').includes('text/event-stream')) {
        const line = text.split('\n').find((l) => l.startsWith('data:')); return line ? JSON.parse(line.slice(5)) : {};
      }
      return JSON.parse(text);
    };
    const init = await post({ jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'market-site', version: '1' } } });
    if (init.error) throw new Error(init.error.message);
    await post({ jsonrpc: '2.0', method: 'notifications/initialized' });
    const res = await post({ jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name: tool, arguments: args } });
    if (res.error) throw new Error(res.error.message);
    return res.result;
  }

  function livePane(item) {
    const calls = item.examples.calls.filter((c) => c.tool === item.live.tool);
    const base = getBase(), url = base + item.endpoint;
    const out = h('div', {});
    const cross = new URL(url, location.href).origin !== location.origin;
    out.append(h('div', { class: 'note', text: `这会用你的 token 真的调用 ${url}。token 只保存在当前标签页的内存/会话里，页面不会把它写到磁盘或发给别处。` }));
    if (cross) out.append(h('div', { class: 'note bad', text: '服务地址和本站不同源，浏览器可能因跨域限制拒绝请求。请把本站和 MCP 部署在同一个域名下，或改用“调用说明”里的方式。' }));
    const token = h('input', { type: 'password', autocomplete: 'off', placeholder: 'Bearer token', value: sess.get('market.token') || '', style: 'width:320px;max-width:100%', 'aria-label': 'token' });
    const sel = h('select', { 'aria-label': '示例' }, calls.map((c, i) => h('option', { value: i, text: c.title })));
    const ta = h('textarea', { 'aria-label': '参数 JSON', spellcheck: 'false' });
    const output = h('div', { class: 'out' });
    const fill = () => { ta.value = JSON.stringify(calls[+sel.value].arguments, null, 2); };
    sel.addEventListener('change', fill); fill();
    const run = h('button', { type: 'button', class: 'primary', text: '运行', onclick: async () => {
      let args; try { args = JSON.parse(ta.value); } catch (e) { output.replaceChildren(h('div', { class: 'note bad', text: `参数不是合法 JSON：${e.message}` })); return; }
      if (!token.value.trim()) { output.replaceChildren(h('div', { class: 'note bad', text: '请先填写 token' })); return; }
      sess.set('market.token', token.value.trim()); run.disabled = true; output.replaceChildren(h('div', { class: 'meta', text: '调用中…' }));
      try {
        const t0 = performance.now(); const res = await mcpCall(url, token.value.trim(), item.live.tool, args);
        const ms = Math.round(performance.now() - t0), nodes = [h('div', { class: res.isError ? 'note bad' : 'note ok', text: `${res.isError ? '工具返回错误（isError）' : '成功'} · ${ms} ms` })];
        for (const c of res.content || []) {
          nodes.push(...contentNodes([c]));
          if (c.type === 'resource_link' && /^https?:\/\//.test(c.uri)) nodes.push(h('p', {}, h('a', { href: c.uri, target: '_blank', rel: 'noopener noreferrer', text: `下载 ${c.name || '文件'}` })));
        }
        output.replaceChildren(...nodes);
      } catch (e) { output.replaceChildren(h('div', { class: 'note bad', text: `调用失败：${e.message}` })); }
      finally { run.disabled = false; }
    } });
    out.append(h('div', { class: 'tools' }, token, sel, run), ta, h('h3', { text: '结果' }), output);
    return out;
  }

  // ---------- 启动 ----------
  async function boot() {
    try {
      const r = await fetch('data/catalog.json', { cache: 'no-cache' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      CAT = await r.json();
    } catch (e) { app.textContent = `加载数据失败：${e.message}。请先运行 python site/build.py，并通过 http 访问本页（不要直接用 file:// 打开）。`; return; }
    document.getElementById('brand').textContent = CAT.config.title;
    baseInput.placeholder = CAT.config.baseUrl || (location.protocol.startsWith('http') ? location.origin : CAT.config.exampleBaseUrl);
    baseInput.value = local.get('market.baseUrl') || '';
    // 只有值真的变了才重绘：否则用户在输入框里输入后点页面上的按钮，失焦触发的 change 会把整页重绘，这次点击就丢了
    let lastBase = baseInput.value.trim();
    baseInput.addEventListener('change', () => {
      const v = baseInput.value.trim(); if (v === lastBase) return;
      lastBase = v; local.set('market.baseUrl', v); render();
    });
    window.addEventListener('hashchange', render);
    render();
  }
  boot();
})();
