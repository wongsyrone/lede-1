// Run with Node: test_view.js path/to/turboacc.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = fs.readFileSync(process.argv[2], 'utf8');

function render(features) {
	const options = {};
	const section = {
		option(type, name) {
			const values = [];
			options[name] = values;
			return { value(key) { values.push(key); }, depends() {} };
		}
	};
	const form = {
		Map: function() {
			this.section = () => section;
			this.render = () => options;
		}
	};
	const view = new Function('form', 'rpc', 'view', '_', source)(
		form, { declare() {} }, { extend: value => value }, value => value
	);
	return view.render([null, { hasTCPCCA: 'cubic', ...features }, null]);
}

assert.deepEqual(render({}).fullcone, ['0']);
assert.deepEqual(render({ hasBRCMFULLCONENAT: true }).fullcone, ['0', '2']);
for (const feature of ['hasXTFULLCONENAT', 'hasNFTFULLCONENAT'])
	assert.deepEqual(render({ [feature]: true, hasBRCMFULLCONENAT: true }).fullcone, ['0', '1', '2']);
assert.deepEqual(render({ hasXTFULLCONENAT: true }).fullcone, ['0', '1']);
assert.deepEqual(render({ hasFLOWOFFLOADING: true }).fastpath, ['disabled', 'flow_offloading']);
assert.deepEqual(render({ hasSHORTCUTFECM: true }).fastpath, ['disabled', 'shortcut_fe_cm']);
console.log('TurboACC view: 7 capability cases passed.');
