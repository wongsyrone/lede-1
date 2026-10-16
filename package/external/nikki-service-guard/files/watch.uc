#!/usr/bin/ucode -S
'use strict';

import * as fs from 'fs';
import * as ubus from 'ubus';
import * as uloop from 'uloop';

uloop.init();
let bus = ubus.connect();
if (!bus)
	exit(1);

let pending = false;
let debounce = uloop.timer(0, () => {
	pending = false;
	// All writes, including provider API requests, run under the native Nikki lock.
	system(['/usr/libexec/nikki-service-guard', 'sync']);
});
function schedule() {
	if (!pending) {
		pending = true;
		debounce.set(1000);
	}
}
let sub = bus.subscriber((event) => {
	if (event?.data?.name != 'nikki-service-guard')
		schedule();
}, () => schedule());
if (!sub || !sub.subscribe('service'))
	exit(1);

let timer = uloop.timer(1, function() {
	if (!bus.call('service', 'list', { name: 'nikki' }))
		exit(1); // procd reconnects the watcher after ubus restarts.
	schedule();
	this.set(5000);
});
uloop.run();
