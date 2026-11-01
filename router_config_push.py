import yaml
import ipaddress
from jinja2 import Environment, FileSystemLoader
import os
from netmiko import ConnectHandler, NetmikoAuthenticationException, NetmikoTimeoutException
import getpass
def is_valid_ip(value):
	try:
		ipaddress.ip_address(value)
		return True
	except ValueError:
		return False
def is_valid_network(value):
	try:
		if value == "any":
			return True
		ipaddress.ip_network(value, strict=False)
		return True
	except ValueError:
		return False
def validate_device(device):
	error_check = []
	hostname = device.get('hostname', 'UNKNOWN_HOST')
	mgmt_ip = device.get('mgmt_ip', 'INVALID_IP')
	device_type = device.get('device_type', 'UNKNOWN_DEVICE')
	if " " in hostname:
		error_check.append(f"Spaces found in '{hostname}'")
	if not is_valid_ip(mgmt_ip):
		error_check.append(f"INVALID MANAGEMENT IP: on {hostname} error {mgmt_ip}")
	acl_name = []
	for acl in device.get('acl_list', []):
		acl_name.append(acl.get('name'))
		name_acl = acl.get('name', 'UNKNOWN_NAME')
		rules = acl.get('rules', [])
		for rule in rules:
			rule_number = rule.get('rule_number', 'NOT_VALID')
			action = rule.get('action', 'UNSUPPORTED_ACTION')
			source = rule.get('source', 'INVALID_NETWORK')
			destination = rule.get('destination', 'INVALID_NETWORK')
			if action not in ['permit', 'deny']:
				error_check.append(f"WARNING at '{hostname}':Rule Number: '{rule_number}' '{name_acl}' INVALID action '{action}' entry")
			if not is_valid_network(source):
				error_check.append(f"INVALID CIDR: on {hostname} {rule_number} {name_acl} check Source error {source}")
			if not is_valid_network(destination):
				error_check.append(f"INVALID CIDR: on {hostname} {rule_number} {name_acl} check Destination error {destination}")
	for intf in device.get('interfaces', []):
		name = intf.get('name', 'UNKNOWN_NAME')
		acl_in = intf.get('acl_in')
		ip_addr = intf.get('ip_addr', 'NOT_VALID')
		if acl_in and acl_in not in acl_name:
			error_check.append(f"Device {hostname} Interface {name}: ACL '{acl_in}' not defined")
		if not is_valid_ip(ip_addr):
			error_check.append(f"INVALID IP ADDRESS: on {hostname} Interface '{name}' check {ip_addr}")
	for static in device.get('static_routes', []):
		network = static.get('network', 'INVALID IP')
		mask = static.get('mask', 'INVALID_MASK')
		next_hop = static.get('next_hop', 'INVALID_IP')
		if not is_valid_ip(network):
			error_check.append(f"INVALID Static IP ADDRESS: on {hostname} check {network} {mask} {next_hop}")
		if not is_valid_ip(next_hop):
			error_check.append(f"INVALID Next Hop ADDRESS: on {hostname} check {next_hop}")
	return error_check
def wildcard(value):
	if value == "any":
		return value
	net = ipaddress.ip_network(value, strict= False)
	return f"{net.network_address} {net.hostmask}"
def main():
	with open('router_reference.yaml', 'r') as f:
		data = yaml.safe_load(f)

	env = Environment(loader = FileSystemLoader('.'))
	env.filters['wildcard'] = wildcard
	template = env.get_template('router_reference.j2')

	output_dir = 'router_reference'
	os.makedirs(output_dir, exist_ok = True)

	username = os.environ.get('NET_USER') or input('username: ')
	password = getpass.getpass(prompt = f"Password for '{username}': ")
	summary = {}

	devices =data.get('devices', [])
	for device in devices:
		hostname = device.get('hostname', 'UNKNOWN_HOST')
		device_type = device.get('device_type', 'UNKNOWN_DEVICE')
		mgmt_ip = device.get('mgmt_ip', 'NOT_AVAILABLE')
		enabled = device.get('enabled', False)
		file_path = os.path.join(output_dir, f"{hostname}.cfg")

		if not enabled:
			print(f"SKIPPING configuration on device '{hostname}': Device not enabled")
			summary[hostname] = "Skipped Device (disabled)"
			continue

		error_check = validate_device(device)
		if error_check:
			print(f"[INVALID] {hostname}: ")
			for error in error_check:
				print(f" -{error}")
			summary[hostname] = "Skipped (invalid data)"
			continue
		rendered_config = template.render(device)
		config_commands = rendered_config.splitlines()
		with open(file_path, 'w') as f_out:
			f_out.write(rendered_config)
		print(f"[SUCCESS] configuration copied on {file_path}")

		cisco_device = {
			'device_type': device_type,
			'host': mgmt_ip,
			'username': username,
			'password': password,
		}

		try:
			net_connect = ConnectHandler(**cisco_device)
			print(f"[NETMIKO] Connected successfully. Prompt {net_connect.find_prompt()}")
			net_connect.send_config_set(config_commands)
			net_connect.save_config()
			print("\n---------CONFIGURATION PUSH LOG--------------------")
			print("----------------------------------------------------\n")

			print(f"[NETMIKO] Verifying deployment with operational command")
			verify_output = net_connect.send_command("show ip interface brief")
			name_on_interface = []
			for line in verify_output.splitlines():
				parts = line.split()
				if parts:
					name_on_interface.append(parts[0])
			missing = []
			for intf in device.get('interfaces', []):
				intf_name = intf.get('name', 'UNKNOWN')
				if intf_name not in name_on_interface:
					missing.append(intf_name)
			net_connect.disconnect()
			if missing:
				summary[hostname] = f"PUSHED VERIFY FAILED (missing interface) {missing}"
			else:
				summary[hostname]= 'PUSHED, VERIFIED'


		except NetmikoTimeoutException:
			summary[hostname] = "Failed (timeout)"
		except NetmikoAuthenticationException:
			summary[hostname] = "Failed (Authentication)"
		except Exception as e:
			summary[hostname] = f"Failed ({e})"

	print("\n" + "=" *50)
	print("SUMMARY")
	print("=" *50)
	for hostname, result in summary.items():
		print(f"{hostname}: {result}")
if __name__ == "__main__":
	main()
