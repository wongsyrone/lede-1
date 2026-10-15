require 'yaml'
require 'digest'

package = File.expand_path('..', __dir__)
profile = YAML.safe_load_file(File.join(package, 'files/default.yaml'), aliases: true)
providers = profile.fetch('rule-providers')
groups = profile.fetch('proxy-groups')
group_names = groups.map { |g| g.fetch('name') }
raise 'duplicate groups' unless group_names.uniq == group_names
raise 'missing classification groups' unless groups.length == 43
raise 'embedded private proxies' unless profile.fetch('proxies').empty?
raise 'nonempty public node file' unless YAML.safe_load_file(File.join(package, 'files/user.yaml')) == {'proxies' => []}
raise 'Nikki owns listeners and routing' if (profile.keys & %w[tun listeners external-controller secret interface-name]).any?
raise 'IPv6 inconsistency' unless profile['ipv6'] && profile.fetch('dns')['ipv6']

scan = lambda do |value|
  case value
  when Hash
    raise 'private field' if (value.keys & %w[password secret token uuid username]).any?
    value.each_value { |item| scan.call(item) }
  when Array
    value.each { |item| scan.call(item) }
  when String
    raise 'desktop or corporate residue' if value.match?(/hbis-|ec-socks|direct-nic|direct-apps|PROCESS-NAME|Windows NT/)
  end
end
scan.call(profile)

references = []
targets = group_names + %w[DIRECT REJECT]
groups.each do |group|
  raise 'unresolved group proxy' unless (group.fetch('proxies', []) - targets).empty?
  raise 'unresolved node provider' unless (group.fetch('use', []) - profile.fetch('proxy-providers').keys).empty?
  if %w[url-test fallback].include?(group.fetch('type'))
    raise 'DIRECT must not win automatic proxy selection' if group.fetch('proxies', []).include?('DIRECT')
  end
end
profile.fetch('rules').each do |rule|
  fields = rule.split(',')
  references << fields[1] if fields[0] == 'RULE-SET'
  target = fields[0] == 'MATCH' ? fields[1] : fields[2]
  raise "unresolved rule target: #{target}" unless targets.include?(target)
end
dns = profile.fetch('dns')
raise 'local DNS loopback not explicit' unless dns.fetch('nameserver-policy').fetch('+.lan,+.local,+.in-addr.arpa,+.ip6.arpa') == ['127.0.0.1:53']
dns.fetch('nameserver-policy').each_key do |key|
  references.concat(key.delete_prefix('rule-set:').split(',')) if key.start_with?('rule-set:')
end
dns.fetch('fake-ip-filter').each do |key|
  references.concat(key.delete_prefix('rule-set:').split(',')) if key.start_with?('rule-set:')
end
raise 'unresolved rule provider' unless (references.uniq - providers.keys).empty?
raise 'unused provider' unless (providers.keys - references.uniq).empty?
raise 'unused cn-ip' if providers.key?('cn-ip')

pins = File.read(File.join(package, 'rules.mk'))
revision = pins[/^RULES_REV:=([a-f0-9]{40})$/, 1]
raise 'missing immutable source' unless revision
downloads = pins.scan(/^\$\(eval \$\(call RuleDownload,([^,]+),([^,]+),([a-f0-9]{64})\)\)$/).to_h { |name, path, hash| [name, [path, hash]] }
providers.each do |name, provider|
  path = provider.fetch('path')
  raise 'provider escapes Nikki directory' unless File.dirname(path) == '/etc/nikki/run/providers/rule'
  if provider['type'] == 'http'
    source, hash = downloads.fetch(name)
    raise 'incorrect runtime URL' unless provider['url'] == "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/meta/#{source}"
    raise 'snapshot path mismatch' unless File.basename(path) == "#{name}.mrs"
    raise 'rule bootstrap depends on a proxy' unless provider['proxy'] == 'DIRECT'
    if ENV['RULES_DIR']
      file = File.join(ENV.fetch('RULES_DIR'), "nikki-rule-#{revision}-#{name}.mrs")
      raise 'snapshot hash mismatch' unless Digest::SHA256.file(file).hexdigest == hash
    end
  else
    data = YAML.safe_load_file(File.join(package, 'files/rules', File.basename(path)))
    raise 'duplicate local rules' unless data.fetch('payload').uniq == data['payload']
  end
end
raise 'unreferenced downloads' unless downloads.keys.sort == providers.select { |_, p| p['type'] == 'http' }.keys.sort

puts "OK: #{groups.length} groups, #{profile.fetch('rules').length} rules, #{downloads.length} pinned MRS and #{providers.length - downloads.length} local providers"
