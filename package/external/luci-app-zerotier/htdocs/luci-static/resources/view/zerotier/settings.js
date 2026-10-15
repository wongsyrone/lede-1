'use strict';
'require form';
'require poll';
'require rpc';
'require uci';
'require view';

var callStatus = rpc.declare({
	object: 'luci.zerotier',
	method: 'get_status',
	reject: true
});

return view.extend({
	load: function() {
		return uci.load('zerotier');
	},

	render: function() {
		var section = uci.get('zerotier', 'openwrt_network');

		if (!section || section['.type'] !== 'zerotier')
			throw new Error(_('The zerotier.openwrt_network configuration section is missing or has an unexpected type.'));

		var m = new form.Map('zerotier', _('ZeroTier'),
			_('ZeroTier is an open source, cross-platform virtual LAN.'));
		var s = m.section(form.NamedSection, 'openwrt_network', 'zerotier');
		var o;

		s.addremove = false;

		[
			[ 'enabled', _('Enable'), '0' ],
			[ 'allowDNS', _("Let ZeroTier modify the system's DNS settings"), '1' ],
			[ 'allowDefault', _("Let ZeroTier modify the system's default route"), '0' ],
			[ 'allowGlobal', _("Let ZeroTier manage IP addresses and route assignments that aren't in private ranges (rfc1918)"), '1' ],
			[ 'allowManaged', _('Let ZeroTier manage IP addresses and route assignments'), '1' ]
		].forEach(function(option) {
			var flag = s.option(form.Flag, option[0], option[1]);
			flag.default = option[2];
			flag.rmempty = false;
		});

		o = s.option(form.Value, 'port', _('Port'));
		o.datatype = 'and(uinteger,max(65535))';
		o.default = '9993';
		o.optional = true;
		o.rmempty = true;

		o = s.option(form.DynamicList, 'join', _('ZeroTier Network ID'));
		o.datatype = 'and(hexstring,length(16))';
		o.rmempty = false;

		o = s.option(form.Value, 'secret', _('Secret'));
		o.password = true;
		o.optional = true;
		o.default = '';
		o.rmempty = false;

		o = s.option(form.Value, 'public_portion', _('Public portion'));
		o.optional = true;
		o.default = '';
		o.rmempty = false;

		o = s.option(form.Flag, 'nat', _('Auto NAT Clients'),
			_('Allow ZeroTier clients to access your LAN network.'));
		o.default = '0';
		o.rmempty = false;

		o = s.option(form.DummyValue, '_manage', _('Manage networks'),
			_('Create or manage your ZeroTier networks and authorize clients.'));
		o.renderWidget = function() {
			return E('a', {
				'href': 'https://my.zerotier.com/network',
				'target': '_blank',
				'rel': 'noopener noreferrer',
				'class': 'cbi-button cbi-button-apply'
			}, _('ZeroTier Central'));
		};

		return m.render().then(function(formNode) {
			var status = E('p', { 'role': 'status' }, _('Collecting data...'));

			poll.add(function() {
				return callStatus().then(function(data) {
					if (!data || typeof data.running !== 'boolean')
						throw new Error(_('Invalid service status response.'));

					status.textContent = data.running
						? _('The ZeroTier service is running.')
						: _('The ZeroTier service is not running.');
				}).catch(function(error) {
					status.textContent = _('Service status unknown: ') + error.message;
				});
			}, 5);

			return E('div', {}, [ status, formNode ]);
		});
	}
});
