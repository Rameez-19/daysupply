// Execute every shipped script against a permissive DOM. Syntax checking
// cannot find an identifier that does not exist; only running the file can.
const fs = require('fs');
const el = () => ({
  style: {}, dataset: {}, options: [], value: '', textContent: '',
  innerHTML: '', hidden: false, selectedIndex: 0, parentElement: null,
  classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
  appendChild() {}, addEventListener() {}, querySelectorAll: () => [],
  getContext: () => ({}),
});
global.window = { addEventListener() {}, location: { hash: '', search: '' } };
global.document = { getElementById: () => el(), querySelector: () => el(),
                    querySelectorAll: () => [], addEventListener() {},
                    createElement: () => el() };
global.navigator = { onLine: true,
  serviceWorker: { register: () => Promise.resolve({}),
                   getRegistrations: async () => [] } };
global.indexedDB = { open: () => ({}) };
global.fetch = async () => ({ ok: true, json: async () => ({}) });
global.Chart = function () { return { destroy() {} }; };
global.history = { replaceState() {} };
global.location = { reload() {}, pathname: '/', search: '', hash: '' };
global.caches = null;
process.on('unhandledRejection', () => {});

let failed = 0;
for (const f of process.argv.slice(2)) {
  try {
    new Function(fs.readFileSync(f, 'utf8'))();
  } catch (e) {
    failed++;
    console.log(`${f}: ${e.constructor.name}: ${e.message}`);
  }
}
process.exit(failed ? 1 : 0);
