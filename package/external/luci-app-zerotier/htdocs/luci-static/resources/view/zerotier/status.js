'use strict';
'require poll';
'require rpc';
'require view';

var callInterfaces = rpc.declare({
	object: 'luci.zerotier',
	method: 'get_interfaces',
	reject: true
});

var callNetworks = rpc.declare({
	object: 'luci.zerotier',
	method: 'get_networks',
	reject: true
});

var callPeers = rpc.declare({
	object: 'luci.zerotier',
	method: 'get_peers',
	reject: true
});

function interfaceText(data) {
	if (!data || !data.devices || typeof data.devices !== 'object')
		throw new Error(_('Invalid interface response.'));

	return Object.keys(data.devices).sort().map(function(name) {
		var device = data.devices[name];
		var addresses = (device.ipaddrs || []).concat(device.ip6addrs || []);

		return name + ': ' + (device.up ? _('Up') : _('Down')) +
			'\n  MAC: ' + (device.mac || '-') +
			'\n  ' + addresses.map(function(address) {
				return address.address + '/' + address.netmask;
			}).join('\n  ');
	}).join('\n\n') || _('No ZeroTier interfaces.');
}

function commandText(data) {
	if (!data || typeof data.code !== 'number')
		throw new Error(_('Invalid command response.'));

	if (data.code !== 0)
		throw new Error(data.stderr || data.stdout || _('Command failed with exit code ') + data.code);

	return data.stdout || _('No data.');
}

function update(node, request, format) {
	return request.then(function(data) {
		node.textContent = format(data);
	}).catch(function(error) {
		node.textContent = _('Query failed: ') + error.message;
	});
}

return view.extend({
	render: function() {
		var interfaces = E('pre', {}, _('Collecting data...'));
		var networks = E('pre', {}, _('Collecting data...'));
		var peers = E('pre', {}, _('Collecting data...'));

		poll.add(function() {
			return Promise.all([
				update(interfaces, callInterfaces(), interfaceText),
				update(networks, callNetworks(), commandText),
				update(peers, callPeers(), commandText)
			]);
		}, 5);

		return E('div', { 'class': 'cbi-map' }, [
			E('h2', {}, _('ZeroTier')),
			E('div', { 'class': 'cbi-section' }, [
				E('h3', {}, _('Interfaces')), interfaces
			]),
			E('div', { 'class': 'cbi-section' }, [
				E('h3', {}, _('Joined networks')), networks
			]),
			E('div', { 'class': 'cbi-section' }, [
				E('h3', {}, _('Peers')), peers
			])
		]);
	},

	handleSave: null,
	handleSaveApply: null,
	handleReset: null
});
