'use strict';

import * as fs from 'fs';
import { cursor } from 'uci';
import { connect } from 'ubus';
import { sha256 } from 'digest';
import { runtime, down_prefix, check, identifier, quote, read_yaml, atomic, atomic_text,
	domain, real_address, nodes, ready, request, withdrawn } from './common.uc';

let state = {};
let managed = [];
let current_profile;

function capture(argv) {
	let pipe = fs.popen(join(' ', map(argv, quote)) + ' 2>/dev/null', 'r');
	check(pipe != null, 'cannot run system helper');
	let text = pipe.read('all');
	check(pipe.close() == 0, 'system helper failed');
	return text;
}

function nft_table(name) {
	let pipe = fs.popen('nft -s list table inet ' + name + ' 2>/dev/null', 'r');
	let text = pipe?.read('all');
	return pipe?.close() == 0 ? text : '';
}

function nft_apply(name, body) {
	let previous = nft_table(name);
	let text = (length(previous) ? 'delete table inet ' + name + '\n' : '') + body;
	let path = runtime + '/transaction.nft';
	check(fs.writefile(path, text) == length(text), 'cannot write nft transaction');
	check(system(['nft', '-c', '-f', path]) == 0, 'invalid nft transaction');
	check(system(['nft', '-f', path]) == 0, 'nft transaction failed');
	check(length(nft_table(name)) > 0, 'nft table missing after commit');
}

function running(service) {
	return filter(values(service?.instances ?? {}), (i) => i.running && i.pid > 0
		&& fs.stat('/proc/' + i.pid) != null);
}

function addresses(bus) {
	let result = ['127.0.0.1', '::1'];
	let interfaces = bus.call('network.interface', 'dump', {})?.interface ?? [];
	for (let net in interfaces)
		for (let key in ['ipv4-address', 'ipv6-address'])
			for (let address in net[key] ?? [])
				push(result, address.address);
	return uniq(result);
}

function mappings(uci, local_addresses, prepare) {
	let result = [];
	let seen = {};
	uci.foreach('nikki_service_guard', 'proxy', (cfg) => {
		if (cfg.enabled != '1')
			return;
		check(identifier(cfg.service) && cfg.service != 'nikki' && identifier(cfg.provider),
			'invalid managed service or provider');
		check(!seen[cfg.service] && !seen[cfg.provider], 'duplicate managed service or provider');
		seen[cfg.service] = seen[cfg.provider] = true;
		let source = cfg.source;
		check(type(source) == 'string'
			&& match(source, /^\/etc\/nikki\/guard\/providers\/[A-Za-z0-9_-]+\.yaml$/),
			'invalid private provider path');
		check(fs.realpath(source) == source, 'private provider must be a regular owned file');
		let info = fs.stat(source);
		check(info?.type == 'file' && info.uid == 0 && !(info.mode & 0022), 'unsafe private provider ownership');
		let native = cfg.native_config;
		let remote = null;
		let native_hash = null;
		if (native) {
			check(type(native) == 'string' && match(native, /^\/etc\/[A-Za-z0-9_./-]+\.json$/)
				&& index(native, '..') < 0 && fs.realpath(native) == native && identifier(cfg.domain_key),
				'invalid native configuration path or key');
			let body = fs.readfile(native);
			check(body != null && length(body) <= 1048576, 'cannot read native configuration');
			remote = domain(json(body)[cfg.domain_key]);
			native_hash = sha256(body);
		}
		push(result, {
			service: cfg.service, provider: cfg.provider,
			path: runtime + '/' + cfg.provider + '.yaml',
			// Preparation publishes only REJECT; live locality is checked before admission.
			nodes: prepare ? [] : nodes(read_yaml(source), local_addresses), domain: remote, native_hash,
		});
	});
	return result;
}

function selectors(uci) {
	let identity = [];
	let users = map(split(fs.readfile('/etc/passwd') ?? '', '\n'), (s) => split(s, ':')[0]);
	let groups = map(split(fs.readfile('/etc/group') ?? '', '\n'), (s) => split(s, ':')[0]);
	function array(v) { return type(v) == 'array' ? v : v == null ? [] : [v]; }
	uci.foreach('nikki', 'router_access_control', (cfg) => {
		if (cfg.enabled != '1')
			return;
		let live = [];
		for (let path in array(cfg.cgroup)) {
			check(match(path, /^services\/[A-Za-z0-9_-]+(\/[A-Za-z0-9_-]+)*$/)
				&& path != 'services/nikki', 'unsupported cgroup selector');
			let info = fs.stat('/sys/fs/cgroup/' + path);
			if (info?.type == 'directory') {
				push(live, path);
				push(identity, [path, info.inode]);
			}
		}
		if (cfg.proxy == '0' || cfg.dns == '0') {
			check(length(live) || length(filter(array(cfg.user), (v) => index(users, v) >= 0 && v != 'root'))
				|| length(filter(array(cfg.group), (v) => index(groups, v) >= 0 && v != 'root')),
				'bypass would become unconditional');
			check(index(array(cfg.user), 'root') < 0 && index(array(cfg.group), 'root') < 0,
				'root-wide bypass is unsupported');
		}
	});
	return identity;
}

function dns_guard(uci, bus, state) {
	let enabled = uci.get('nikki', 'config', 'enabled') == '1'
		&& uci.get('nikki', 'proxy', 'enabled') == '1';
	if (!enabled) {
		if (length(nft_table('nikki_dns_guard')))
			check(system(['nft', 'delete', 'table', 'inet', 'nikki_dns_guard']) == 0, 'cannot disable DNS guard');
		state.dns_policy = state.dns_rules = null;
		return; // An explicit disable is a user decision; faults never change this setting.
	}
	let interfaces = uci.get('nikki', 'proxy', 'lan_inbound_interface') ?? ['lan'];
	if (type(interfaces) != 'array')
		interfaces = [interfaces];
	let devices = [];
	for (let name in interfaces) {
		let net = bus.call('network.interface', 'status', { interface: name });
		let device = net?.l3_device ?? net?.device ?? uci.get('network', name, 'device');
		check(type(device) == 'string' && match(device, /^[A-Za-z0-9_.:-]{1,15}$/), 'invalid managed LAN device');
		push(devices, sprintf('"%s"', device));
	}
	check(length(devices), 'no managed LAN device');
	let body = 'table inet nikki_dns_guard {\n'
		+ 'chain output { type filter hook output priority filter - 1; policy accept;\n'
		+ 'oifname != "lo" meta l4proto { tcp, udp } th dport 53 counter drop\n}\n'
		+ 'chain forward { type filter hook forward priority filter - 1; policy accept;\n'
		+ 'iifname { ' + join(', ', uniq(devices)) + ' } meta l4proto { tcp, udp } th dport 53 counter drop\n}\n'
		+ 'chain dstnat { type nat hook prerouting priority dstnat - 1; policy accept;\n'
		+ 'iifname { ' + join(', ', uniq(devices)) + ' } meta l4proto { tcp, udp } th dport 53 counter redirect to :1053\n}\n}\n';
	let hash = sha256(body);
	let actual = nft_table('nikki_dns_guard');
	if (state.dns_policy != hash || !length(actual) || state.dns_rules != sha256(actual))
		nft_apply('nikki_dns_guard', body);
	state.dns_policy = hash;
	state.dns_rules = sha256(nft_table('nikki_dns_guard'));
}

function validate_profile(profile, proxies) {
	let dns = profile.dns;
	check(dns?.enable && dns['enhanced-mode'] == 'fake-ip' && dns['listen'] == '[::]:1053',
		'managed profile requires the standard fake-IP DNS listener');
	check(type(dns['fake-ip-range']) == 'string', 'effective fake-IP range must be explicit');
	real_address('127.0.0.1', dns); // Validate both configured CIDRs before admitting any service.
	check(index(dns['fake-ip-filter'] ?? [], 'rule-set:external-proxy-domains') >= 0,
		'native domains must bypass fake-IP');
	let policies = dns['nameserver-policy'];
	check(keys(policies ?? {})[0] == 'rule-set:external-proxy-domains',
		'native DNS policy must precede classification policies');
	let local = keys(policies ?? {})[1];
	check(type(local) == 'string' && index(local, '+.lan,+.local,') == 0
		&& sprintf('%.J', policies[local]) == sprintf('%.J', ['127.0.0.1:53']),
		'local authority must precede classification policies');
	for (let field in ['default-nameserver', 'proxy-server-nameserver', 'nameserver', 'direct-nameserver']) {
		let pool = dns[field];
		check(type(pool) == 'array' && length(pool), 'missing encrypted DNS pool');
		for (let ns in pool)
			check(type(ns) == 'string' && match(ns, /^(https|tls):\/\//), 'plaintext DNS pool is unsupported');
	}
	let upstream = policies['rule-set:external-proxy-domains'];
	check(type(upstream) == 'array' && length(upstream), 'missing independent native DNS policy');
	for (let ns in upstream)
		check(match(ns, /^(https|tls):\/\/[^#]+#DIRECT$/), 'native DNS upstream must be encrypted and direct');
	let domain_provider = profile['rule-providers']?.['external-proxy-domains'];
	check(domain_provider?.type == 'file' && domain_provider.behavior == 'domain'
		&& domain_provider.format == 'yaml' && domain_provider.path == runtime + '/domains.yaml',
		'managed domain provider path mismatch');
	for (let proxy in proxies) {
		let provider = profile['proxy-providers']?.[proxy.provider];
		check(provider?.type == 'file' && provider.path == proxy.path, 'managed proxy provider path mismatch');
	}
}

function proxy_guard(proxies, allowed) {
	if (!fs.stat('/sys/fs/cgroup/services/nikki'))
		return;
	let rules = [];
	for (let proxy in proxies)
		for (let node in proxy.nodes) {
			if (index(allowed[proxy.service] ?? [], node.name) >= 0)
				continue;
			check(iptoarr(node.server) && type(node.port) == 'int'
				&& node.port > 0 && node.port <= 65535, 'invalid quarantine endpoint');
			push(rules, 'socket cgroupv2 level 2 "services/nikki" '
				+ (index(node.server, ':') >= 0 ? 'ip6' : 'ip') + ' daddr ' + node.server
				+ ' meta l4proto { tcp, udp } th dport ' + node.port + ' counter reject');
		}
	let body = 'table inet nikki_proxy_guard {\nchain output {\n'
		+ 'type filter hook output priority filter - 2; policy accept;\n' + join('\n', uniq(rules)) + '\n}\n}\n';
	let actual = nft_table('nikki_proxy_guard');
	let token = sha256(body + ':' + fs.stat('/sys/fs/cgroup/services/nikki').inode);
	if (state.quarantine != token || !length(actual) || state.quarantine_rules != sha256(actual))
		nft_apply('nikki_proxy_guard', body);
	state.quarantine = token;
	state.quarantine_rules = sha256(nft_table('nikki_proxy_guard'));
}

function provider_names(profile, name) {
	let result = request(profile, 'GET', '/providers/proxies/' + name);
	check(type(result.proxies) == 'array', 'invalid provider readback');
	return sort(map(result.proxies, (p) => p.name));
}

function apply_provider(profile, proxy, desired) {
	let expected = sort(map(desired.proxies, (p) => p.name));
	let changed = atomic(proxy.path, desired);
	let current = provider_names(profile, proxy.provider);
	let token = sha256(sprintf('%.J', desired));
	state.applied ??= {};
	if (changed || state.applied[proxy.provider] != token || sprintf('%.J', current) != sprintf('%.J', expected)) {
		// A timed-out PUT remains unconfirmed even when names match: credentials may have changed.
		let confirmed = false;
		try { request(profile, 'PUT', '/providers/proxies/' + proxy.provider); confirmed = true; } catch (e) {}
		current = provider_names(profile, proxy.provider);
		check(confirmed, 'provider request outcome ambiguous; quarantined until retry');
	}
	check(sprintf('%.J', current) == sprintf('%.J', expected), 'provider update not confirmed');
	state.applied[proxy.provider] = token;
	return changed;
}

function disconnect(profile, names) {
	if (!length(names))
		return;
	for (let conn in request(profile, 'GET', '/connections').connections ?? []) {
		if (!length(filter(conn.chains ?? [], (v) => index(names, v) >= 0)))
			continue;
		check(type(conn.id) == 'string' && match(conn.id, /^[A-Za-z0-9_-]+$/), 'invalid connection identifier');
		request(profile, 'DELETE', '/connections/' + conn.id);
	}
}

function snapshot(proxy) {
	return {
		service: proxy.service, provider: proxy.provider, path: proxy.path,
		nodes: map(proxy.nodes, (n) => ({ name: n.name, server: n.server, port: n.port })),
	};
}

function work() {
	let mode = ARGV[0] ?? 'sync';
	let uci = cursor();
	let bus = connect();
	check(bus != null, 'ubus unavailable');
	if (mode == 'gate' && uci.get('nikki', 'config', 'enabled') != '1'
		&& !length(nft_table('nikki')))
		return; // Explicit standalone use must not depend on a managed provider file.
	try { state = json(fs.readfile(runtime + '/state.json') ?? '{}'); } catch (e) {}
	managed = state.managed ?? [];
	if (mode != 'prepare')
		dns_guard(uci, bus, state);
	let proxies = mappings(uci, addresses(bus), mode == 'prepare');
	let retired = filter(managed, (p) => !length(filter(proxies,
		(v) => v.provider == p.provider && v.service == p.service)));
	// Keep previous endpoints until withdrawal is confirmed, including removed mappings.
	managed = [...managed, ...proxies];
	let tracked = {};
	for (let proxy in managed) {
		let record = snapshot(proxy);
		tracked[sprintf('%.J', record)] = record;
	}
	state.managed = values(tracked);
	let domains = sort(uniq(filter(map(proxies, (p) => p.domain), (v) => v != null)));
	let domain_yaml = length(domains) ? 'payload:\n' + join('', map(domains, (d) => '  - ' + d + '\n')) : 'payload: []\n';
	if (mode == 'prepare') {
		for (let proxy in proxies)
			atomic(proxy.path, withdrawn(proxy.service));
		atomic_text(runtime + '/domains.yaml', domain_yaml);
		return;
	}
	let active = uci.get('nikki', 'config', 'enabled') == '1';
	let all = bus.call('service', 'list', { verbose: true });
	check(all != null, 'service status unavailable');
	let core = running(all.nikki);
	if (!active || !length(core) || !fs.stat('/var/run/nikki/started.flag')) {
		for (let proxy in proxies)
			atomic(proxy.path, withdrawn(proxy.service));
		state.core = null;
		state.admitted = {};
		atomic(runtime + '/state.json', state);
		if (mode == 'gate') {
			let mapped = filter(proxies, (p) => p.service == ARGV[1]);
			// Standalone use is unchanged when Nikki is explicitly disabled and its hijack is gone.
			check(!active && !length(nft_table('nikki')) && length(mapped) == 1, 'Nikki bootstrap is not ready');
		}
		return;
	}
	check(fs.stat('/sys/fs/cgroup/cgroup.controllers'), 'cgroup v2 is required');
	let profile_path = '/etc/nikki/run/config.yaml';
	let profile_hash = sha256(fs.readfile(profile_path) ?? '');
	let profile = read_yaml(profile_path);
	current_profile = profile;
	validate_profile(profile, proxies);
	let identity = selectors(uci);
	let epoch = sprintf('%.J', map(core, (p) => {
		let info = fs.readfile('/proc/' + p.pid + '/stat') ?? '';
		return [p.pid, split(substr(info, rindex(info, ')') + 2), ' ')[19]];
	}));
	let table = nft_table('nikki');
	if (state.core != epoch || !length(table)) {
		check(system(['/bin/sh', '/usr/share/nikki-service-guard/recover.sh']) == 0, 'native routing recovery failed');
		table = nft_table('nikki');
	}
	let rules_token = sha256(sprintf('%.J', identity));
	if (state.cgroups != rules_token || state.rules != sha256(table) || !length(table)) {
		let rendered = capture(['utpl', '-S', '/etc/nikki/ucode/hijack.ut']);
		check(index(rendered, 'table inet nikki {') >= 0, 'native template did not render');
		nft_apply('nikki', rendered);
		table = nft_table('nikki');
	}
	state.cgroups = rules_token;
	state.rules = sha256(table);
	state.core = epoch;
	let domain_changed = atomic_text(runtime + '/domains.yaml', domain_yaml);
	if (domain_changed || state.domains != sha256(sprintf('%.J', domains)) || state.profile != profile_hash) {
		request(profile, 'PUT', '/providers/rules/external-proxy-domains');
		let verified = request(profile, 'GET', '/providers/rules').providers?.['external-proxy-domains'];
		check(verified?.ruleCount == length(domains), 'domain rule update not confirmed');
		// dnsmasq may still hold an answer learned before the native domain changed.
		bus.call('service', 'signal', { name: 'dnsmasq', signal: 1 });
		state.domains = sha256(sprintf('%.J', domains));
	}
	let old_admitted = state.admitted ?? {};
	state.admitted = {};
	state.gates = {};
	state.native ??= {};
	for (let proxy in retired) {
		let permitted = { ...old_admitted, [proxy.service]: [] };
		proxy_guard(managed, permitted);
		atomic(proxy.path, withdrawn(proxy.service));
		if (profile['proxy-providers']?.[proxy.provider])
			apply_provider(profile, proxy, withdrawn(proxy.service));
		disconnect(profile, old_admitted[proxy.service] ?? []);
		delete old_admitted[proxy.service];
	}
	for (let proxy in proxies) {
		let instances = running(all[proxy.service]);
		let cgroup = 'services/' + proxy.service;
		let bypass = index(table, '"' + cgroup + '"') >= 0;
		let valid_config = !proxy.native_hash || length(filter(instances,
			(i) => i.data?.guard_native_checksum == proxy.native_hash)) > 0;
		let gate = bypass && valid_config;
		if (gate && proxy.domain) {
			try {
				let answer = request(profile, 'GET', '/dns/query?name=' + proxy.domain + '&type=A');
				let records = filter(answer.Answer ?? [], (r) => r.type == 1);
				if (!length(records)) {
					answer = request(profile, 'GET', '/dns/query?name=' + proxy.domain + '&type=AAAA');
					records = filter(answer.Answer ?? [], (r) => r.type == 28);
				}
				gate = length(records) > 0 && length(filter(records, (r) => !real_address(r.data, profile.dns))) == 0;
			} catch (e) { gate = false; }
		}
		state.gates[proxy.service] = gate;
		let live = gate && length(instances) ? filter(proxy.nodes, ready) : [];
		let desired = length(live) ? { proxies: live } : withdrawn(proxy.service);
		let unchanged = state.applied?.[proxy.provider] == sha256(sprintf('%.J', desired))
			&& state.native[proxy.service] == proxy.native_hash;
		let permitted = { ...old_admitted, ...state.admitted,
			[proxy.service]: unchanged ? filter(old_admitted[proxy.service] ?? [],
				(n) => length(filter(live, (p) => p.name == n)) > 0) : [] };
		// Close the stale API path before withdrawing it; probes run outside the Mihomo cgroup.
		proxy_guard(managed, permitted);
		check(sha256(fs.readfile(profile_path) ?? '') == profile_hash, 'configuration changed during reconciliation');
		apply_provider(profile, proxy, desired);
		let names = map(live, (p) => p.name);
		disconnect(profile, filter(old_admitted[proxy.service] ?? [], (n) => !unchanged || index(names, n) < 0));
		state.admitted[proxy.service] = names;
		state.native[proxy.service] = proxy.native_hash;
	}
	state.profile = profile_hash;
	proxy_guard(proxies, state.admitted);
	state.managed = map(proxies, snapshot);
	atomic(runtime + '/state.json', state);
	if (mode == 'gate')
		check(state.gates[ARGV[1]], 'native DNS or cgroup bypass is not ready');
}

try { work(); }
catch (error) {
	try { proxy_guard(managed, {}); } catch (ignored) {}
	for (let proxy in managed) {
		try {
			atomic(proxy.path, withdrawn(proxy.service));
			if (current_profile)
				apply_provider(current_profile, proxy, withdrawn(proxy.service));
		} catch (ignored) {}
	}
	state.admitted = {};
	state.gates = {};
	try { atomic(runtime + '/state.json', state); } catch (ignored) {}
	// Only explicitly authored reasons are safe to log.
	let reason = type(error.message) == 'string' && index(error.message, 'guard: ') == 0
		? error.message : 'configuration or reconciliation failed';
	warn('nikki-service-guard: ' + reason + '\n');
	exit(1);
}
