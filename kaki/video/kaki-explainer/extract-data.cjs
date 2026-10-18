const fs = require('fs');
const path = require('path');
const http = require('http');
const { chromium } = require('C:/Users/Admin/AppData/Local/npm-cache/_npx/e41f203b7505f1fb/node_modules/playwright');
const root = path.resolve(__dirname, '../..');
const out = __dirname;
const server = http.createServer((req, res) => {
  const file = path.join(root, decodeURIComponent(req.url.split('?')[0]));
  if (path.relative(root, file).startsWith('..')) return res.writeHead(403).end();
  fs.readFile(file, (err, data) => {
    if (err) return res.writeHead(404).end();
    res.setHeader('Content-Type', file.endsWith('.json') ? 'application/json' : 'text/html; charset=utf-8');
    res.end(data);
  });
});
(async () => {
  fs.mkdirSync(path.join(out, 'reference'), { recursive: true });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1180 }, reducedMotion: 'reduce' });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/kaki-demo.html?api=0`);
  await page.evaluate(() => loadModel());
  const data = await page.evaluate(async () => {
    stopActivity();
    const wa = await scoreText(WA_SCAM_MSG, 'en');
    const calls = [];
    for (let i = 1; i <= CALL_DEMO_LINES.en.length; i++) calls.push(await scoreText(CALL_DEMO_LINES.en.slice(0, i).join(' '), 'en'));
    return {
      strings: STRINGS, message: WA_SCAM_MSG, callLines: CALL_DEMO_LINES,
      messageResult: wa, callResults: calls, modelMeta: S.model.meta,
      screenNames: [...document.querySelectorAll('.scr')].map(e => ({ id: e.id, label: e.getAttribute('aria-label') })),
      styles: [...document.querySelectorAll('style')].map(e => e.textContent).join('\n'),
      symbols: document.querySelector('svg:has(symbol)').outerHTML,
      device: document.querySelector('#device').outerHTML,
      mascot: document.querySelector('#kaki-av svg').outerHTML,
      console: document.querySelector('.console').outerHTML
    };
  });
  const source = fs.readFileSync(path.join(root, 'kaki-demo.html'), 'utf8');
  data.sourceSha256 = require('crypto').createHash('sha256').update(source).digest('hex');
  fs.writeFileSync(path.join(out, 'product-data.json'), JSON.stringify(data, null, 2));
  fs.writeFileSync(path.join(out, 'product-data.js'), 'window.PRODUCT=' + JSON.stringify(data) + ';\n');
  for (const i of [0, 2, 3, 4, 5, 6, 7, 8]) {
    await page.evaluate(i => { stopActivity(); showScreen(i); }, i);
    if (i === 7) await page.evaluate(() => { document.querySelector('#ts-lines').innerHTML = CALL_DEMO_LINES.en.map(x => '<div>' + escapeHtml(x) + '</div>').join(''); });
    await page.locator('#device').screenshot({ path: path.join(out, 'reference', `screen-${i}.png`) });
  }
  await page.evaluate(({score, matchedWords}) => { showScreen(8); triggerScam(score, matchedWords); }, data.messageResult);
  await page.locator('#device').screenshot({ path: path.join(out, 'reference', 'scam-warning.png') });
  await page.screenshot({ path: path.join(out, 'reference', 'demo-console.png'), fullPage: true });
  console.log(JSON.stringify({ message: data.messageResult, calls: data.callResults, screenNames: data.screenNames, errors }));
  await browser.close();
  server.close();
})().catch(e => { console.error(e); server.close(); process.exit(1); });
