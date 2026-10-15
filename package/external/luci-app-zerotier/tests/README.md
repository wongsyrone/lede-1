Run from the luci-app-zerotier package directory:

```sh
node tests/test_views.js
ucode -L "$PWD/tests/mocks" tests/test_rpc.uc
ucode -cdynlink=ubus -o /tmp/luci.zerotier.ucb root/usr/share/rpcd/ucode/luci.zerotier
```

The RPC checks mock the ubus transport and execute the actual ucode plugin.
The view checks mock LuCI's form, RPC and DOM APIs and execute the actual views.
These checks do not replace testing rpcd and the LuCI pages in a running image.
