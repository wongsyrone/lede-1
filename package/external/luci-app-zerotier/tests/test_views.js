'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const app = path.resolve(__dirname, '..');

function loadView(name) {
	const nodes = [], polls = [], calls = [], options = {};
	let response = {}, section = { '.type': 'zerotier' };
	const context = {
		_: text => text,
		E: (tag, attributes, children) => {
			const node = { tag, attributes, children, textContent: '' };
			Object.defineProperty(node, 'innerHTML', {
				set() { throw new Error('Output must be rendered as text'); }
			});
			nodes.push(node);
			return node;
		},
		poll: { add: fn => polls.push(fn) },
		rpc: {
			declare: spec => {
				assert.equal(spec.object, 'luci.zerotier');
				assert.equal(spec.reject, true);
				return () => {
					calls.push(spec.method);
					const value = response[spec.method];
					return value instanceof Error ? Promise.reject(value) : Promise.resolve(value);
				};
			}
		},
		uci: { load: () => Promise.resolve(), get: () => section },
		view: { extend: definition => definition },
		form: {
			Map: function() {
				this.section = () => ({
					option: (type, name) => (options[name] = {})
				});
				this.render = () => Promise.resolve(context.E('form'));
			},
			NamedSection: {}, Flag: {}, Value: {}, DynamicList: {}, DummyValue: {}
		}
	};
	const source = fs.readFileSync(path.join(app, 'htdocs/luci-static/resources/view/zerotier', name + '.js'), 'utf8');
	const view = vm.runInNewContext('(function() {\n' + source + '\n})()', context);
	return {
		view, nodes, polls, calls, options,
		respond: value => { response = value; },
		section: value => { section = value; }
	};
}

async function main() {
	const settings = loadView('settings');
	await settings.view.load();
	await settings.view.render();
	assert.equal(settings.polls.length, 1);
	assert.equal(settings.options.allowDNS.default, '1');
	assert.equal(settings.options.allowDefault.default, '0');
	assert.equal(settings.options.secret.password, true);
	assert.equal(settings.options.join.datatype, 'and(hexstring,length(16))');
	const status = settings.nodes.find(node => node.attributes?.role === 'status');
	for (const running of [ true, false ]) {
		settings.respond({ get_status: { running } });
		const pending = settings.polls[0]();
		assert.equal(typeof pending.then, 'function', 'Polling must wait for the request');
		await pending;
		assert.match(status.textContent, running ? /is running/ : /is not running/);
	}
	for (const result of [ new Error('timeout'), {}, 7 ]) {
		settings.respond({ get_status: result });
		await settings.polls[0]();
		assert.match(status.textContent, /status unknown/);
	}
	settings.section(null);
	assert.throws(() => settings.view.render(), /configuration section/);
	settings.section({ '.type': 'network' });
	assert.throws(() => settings.view.render(), /configuration section/);

	const detail = loadView('status');
	detail.view.render();
	const output = detail.nodes.filter(node => node.tag === 'pre');
	detail.respond({
		get_interfaces: { devices: { zt123: { up: true, mac: 'aa:bb', ipaddrs: [ { address: '10.1.2.3', netmask: '255.255.255.0' } ] } } },
		get_networks: { code: 0, stdout: '<script>literal output</script>' },
		get_peers: new Error('permission denied')
	});
	await detail.polls[0]();
	assert.match(output[0].textContent, /zt123: Up/);
	assert.match(output[0].textContent, /10.1.2.3/);
	assert.equal(output[1].textContent, '<script>literal output</script>');
	assert.match(output[2].textContent, /Query failed: permission denied/);
	detail.respond({
		get_interfaces: { devices: {} },
		get_networks: { code: 0, stdout: '' },
		get_peers: { code: 1, stderr: 'daemon stopped' }
	});
	await detail.polls[0]();
	assert.equal(output[0].textContent, 'No ZeroTier interfaces.');
	assert.equal(output[1].textContent, 'No data.');
	assert.match(output[2].textContent, /Query failed: daemon stopped/);
	detail.respond({
		get_interfaces: new Error('timeout'),
		get_networks: { code: 0, stdout: 'network ready' },
		get_peers: { code: 0, stdout: 'peer ready' }
	});
	await detail.polls[0]();
	assert.match(output[0].textContent, /Query failed: timeout/);
	assert.equal(output[1].textContent, 'network ready');
	assert.equal(output[2].textContent, 'peer ready');
	assert.equal(detail.view.handleSaveApply, null);
	console.log('ZeroTier view checks passed');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
