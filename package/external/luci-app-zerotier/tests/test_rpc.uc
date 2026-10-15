'use strict';

import { realpath } from 'fs';

const state = {};
global.zerotier_test_ubus = {
	defer: function(object, method, args, callback) {
		state.request = { object, method, args };
		callback(state.rc, state.data);
		return 'deferred';
	}
};

const methods = loadfile('root/usr/share/rpcd/ucode/luci.zerotier', {
	raw_mode: true,
	module_search_path: [ realpath('tests/mocks') + '/*.uc' ]
})()['luci.zerotier'];

function invoke(method, rc, data) {
	state.rc = rc;
	state.data = data;
	let reply;
	const deferred = methods[method].call({
		args: { command: '/bin/sh', params: [ '-c', 'false' ] },
		reply: function(data, rc) {
			reply = { data, rc };
		}
	});
	assert(deferred == 'deferred', 'RPC must return the deferred request');
	return reply;
}

assert(length(methods) == 4, 'Only four query methods are exposed');
assert(invoke('get_status', 0, {
	zerotier: { instances: { first: { running: false }, second: { running: true } } }
}).data.running == true);
assert(state.request.object == 'service');
assert(state.request.method == 'list');
assert(state.request.args.name == 'zerotier');
assert(invoke('get_status', 0, {}).data.running == false);
assert(invoke('get_status', 7, null).rc == 7, 'Timeout must not become stopped');

const devices = invoke('get_interfaces', 0, {
	eth0: { up: true },
	zt12345678: { up: true, ipaddrs: [ { address: '10.1.2.3' } ] },
	zt87654321: { up: false }
}).data.devices;
assert(length(devices) == 2 && !exists(devices, 'eth0'));
assert(devices.zt12345678.ipaddrs[0].address == '10.1.2.3');
assert(invoke('get_interfaces', 0, {}).data.devices != null);
assert(invoke('get_interfaces', 6, null).rc == 6);

for (let method, command in { get_networks: 'listnetworks', get_peers: 'peers' }) {
	assert(invoke(method, 0, { code: 0, stdout: '' }).data.code == 0);
	assert(state.request.object == 'file' && state.request.method == 'exec');
	assert(state.request.args.command == '/usr/bin/zerotier-cli');
	assert(length(state.request.args.params) == 1);
	assert(state.request.args.params[0] == command, 'Caller input must not affect the command');
	assert(invoke(method, 0, { code: 1, stderr: 'not running' }).data.code == 1);
	assert(invoke(method, 7, null).rc == 7, 'Propagate timeout');
}

print('ZeroTier RPC checks passed\n');
