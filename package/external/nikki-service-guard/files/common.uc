'use strict';

import * as fs from 'fs';
import * as socket from 'socket';

export const runtime = '/var/run/nikki-service-guard';
export const down_prefix = '__guard_down__';

export function check(condition, reason) {
	if (!condition)
		die('guard: ' + reason);
}

export function identifier(value) {
	return type(value) == 'string' && match(value, /^[A-Za-z0-9_-]{1,64}$/) != null;
}

export function quote(value) {
	return "'" + replace(value, /'/g, "'\\''") + "'";
}

export function read_yaml(path) {
	check(type(path) == 'string' && substr(path, 0, 1) == '/' && !match(path, /[\r\n]/),
		'invalid configuration path');
	let proc = fs.popen('yq -M -o json ' + quote(path) + ' 2>/dev/null', 'r');
	check(proc != null, 'cannot read configuration');
	let data = proc.read('all');
	let status = proc.close();
	check(status == 0 && length(data) <= 2097152, 'cannot parse configuration');
	return json(data);
}

export function atomic_text(path, body) {
	if (fs.readfile(path) == body)
		return false;
	check(fs.writefile(path + '.next', body) == length(body), 'cannot write runtime state');
	check(fs.rename(path + '.next', path), 'cannot publish runtime state');
	return true;
}

export function atomic(path, value) {
	return atomic_text(path, sprintf('%.J\n', value));
}

export function domain(value) {
	check(type(value) == 'string' && length(value) > 0 && length(value) <= 253,
		'invalid native remote address');
	if (iptoarr(value))
		return null;
	value = lc(replace(value, /\.$/, ''));
	let labels = split(value, '.');
	check(length(labels) > 1, 'native remote address must be a fully qualified name or IP');
	for (let label in labels)
		check(match(label, /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/), 'invalid native remote domain');
	return value;
}

export function real_address(value, dns) {
	let address = iptoarr(value);
	if (!address)
		return false;
	let real = true;
	for (let field in ['fake-ip-range', 'fake-ip-range6']) {
		if (!dns[field])
			continue;
		let parts = split(dns[field], '/');
		let network = iptoarr(parts[0]);
		check(length(parts) == 2 && network && match(parts[1], /^[0-9]+$/)
			&& int(parts[1]) <= length(network) * 8, 'invalid effective fake-IP CIDR');
		if (length(network) != length(address))
			continue;
		let remaining = int(parts[1]);
		let matches = true;
		for (let i = 0; i < length(address) && remaining > 0; i++) {
			let bits = min(remaining, 8);
			let mask = (255 << (8 - bits)) & 255;
			if ((address[i] & mask) != (network[i] & mask)) {
				matches = false;
				break;
			}
			remaining -= bits;
		}
		if (matches)
			real = false;
	}
	return real;
}

export function nodes(value, local_addresses) {
	check(type(value) == 'object' && type(value.proxies) == 'array', 'invalid private provider');
	let seen = {};
	for (let node in value.proxies) {
		check(type(node.name) == 'string' && length(node.name) <= 128
			&& length(node.name) && index(node.name, down_prefix) != 0 && !seen[node.name],
			'invalid or duplicate private node name');
		seen[node.name] = true;
		check(node.type == 'socks5' || node.type == 'http', 'only local SOCKS5/HTTP entries are supported');
		check(index(local_addresses, node.server) >= 0, 'proxy listener is not a local router address');
		check(type(node.port) == 'int' && node.port >= 1 && node.port <= 65535, 'invalid local proxy port');
		check(!node.tls && !node['dialer-proxy'], 'unsupported local transport');
	}
	return value.proxies;
}

function conn(host, port, timeout) {
	let s = socket.connect(host, port, { socktype: socket.SOCK_STREAM }, 1000);
	if (s) {
		s.setopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO, { sec: timeout ?? 1, usec: 0 });
		s.setopt(socket.SOL_SOCKET, socket.SO_SNDTIMEO, { sec: 1, usec: 0 });
	}
	return s;
}

export function ready(node) {
	let s = conn(node.server, node.port);
	if (!s)
		return false;
	let result = false;
	if (node.type == 'socks5') {
		let auth = type(node.username) == 'string' && length(node.username) > 0;
		s.send(auth ? chr(5, 1, 2) : chr(5, 1, 0));
		let response = s.recv(2, socket.MSG_WAITALL);
		result = response == (auth ? chr(5, 2) : chr(5, 0));
		if (result && auth) {
			let user = node.username;
			let pass = node.password ?? '';
			result = length(user) <= 255 && length(pass) <= 255;
			if (result) {
				s.send(chr(1, length(user)) + user + chr(length(pass)) + pass);
				result = s.recv(2, socket.MSG_WAITALL) == chr(1, 0);
			}
		}
	}
	else {
		s.send('OPTIONS * HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n\r\n');
		let response = s.recv(128);
		result = response != null && match(response, /^HTTP\/1\.[01] [1-5][0-9][0-9] /) != null;
	}
	s.close();
	return result;
}

export function request(profile, method, path) {
	let endpoint = profile['external-controller'];
	let parts = type(endpoint) == 'string' ? match(endpoint, /^(127\.0\.0\.1|0\.0\.0\.0|\[::1\]|\[::\]):([0-9]+)$/) : null;
	check(parts && int(parts[2]) >= 1 && int(parts[2]) <= 65535, 'local controller required');
	let host = parts[1] == '[::1]' ? '::1' : '127.0.0.1';
	let secret = profile.secret ?? '';
	check(type(secret) == 'string' && !match(secret, /[\r\n]/), 'invalid controller credential');
	let s = conn(host, int(parts[2]), 6);
	check(s != null, 'controller unavailable');
	let headers = `${method} ${path} HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\nContent-Length: 0\r\n`;
	if (length(secret))
		headers += 'Authorization: Bearer ' + secret + '\r\n';
	s.send(headers + '\r\n');
	let response = '';
	for (;;) {
		let part = s.recv(16384);
		if (part == null || length(part) == 0)
			break;
		response += part;
		if (length(response) > 2097152)
			break;
	}
	s.close();
	let status = match(response, /^HTTP\/1\.[01] ([0-9]{3}) /);
	check(status && int(status[1]) >= 200 && int(status[1]) < 300, 'controller request failed');
	let split_at = index(response, '\r\n\r\n');
	check(split_at >= 0 && length(response) <= 2097152, 'invalid controller response');
	let body = substr(response, split_at + 4);
	return length(body) ? json(body) : {};
}

export function withdrawn(service) {
	return { proxies: [{ name: down_prefix + service, type: 'reject' }] };
}
