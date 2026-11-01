# Router Config Automation

Generates Cisco router configurations from YAML data using Jinja2, validates the data before anything is rendered, and pushes the result to each device with Netmiko. Built as a learning project to practise data-driven network automation.

## How it works

For each device in `routers.yaml`, the script does the following, in order:

1. **Skips disabled devices.** A device with `enabled: false` is reported as skipped and nothing is generated for it.
2. **Validates the data.** All problems for a device are collected and printed. If any are found, the device is skipped, so bad data never reaches the template or the network.
3. **Renders the config.** The device's data is passed into the Jinja2 template, and the result is saved to `generated_configs/<hostname>.cfg`.
4. **Pushes the config.** Netmiko connects using the device's `device_type` and `mgmt_ip`, sends the commands, and saves the configuration.
5. **Verifies the result.** It runs `show ip interface brief` and checks that every interface from the YAML appears in the output.
6. **Prints a summary** with one line per device, such as `PUSHED, VERIFIED`, `Failed (timeout)`, `Skipped (invalid data)` or `Skipped Device (disabled)`.

A connection failure on one device is caught and recorded, and the script carries on with the next one.

## What validation checks

- Hostnames contain no spaces
- Management IPs, interface IPs, static route networks and next hops are valid IP addresses
- Every ACL applied to an interface (`acl_in`) is defined on that device
- Every ACL rule action is `permit` or `deny`
- Every ACL rule source and destination is `any` or a valid network in CIDR form

## Files

- `routers.yaml`: the device data (interfaces, ACLs, static routes)
- `router.j2`: the Jinja2 template that turns that data into a config
- `router_config_push.py`: validation, rendering, the push and the summary
- `requirements.txt`: the Python packages needed

The script also has a Jinja2 filter, `wildcard`, which converts a CIDR network such as `10.0.0.0/8` into the address and wildcard mask that IOS ACLs expect (`10.0.0.0 0.255.255.255`).

## Example output

Part of a generated config:

```
hostname al-khaleej-R01
!
ip access-list extended SSH
 remark SSH from management network
 10 permit tcp 172.16.1.0 0.0.0.255 any
 remark Deny all other SSH
 20 deny tcp any any
!
interface GigabitEthernet0/2
 description Up_Link to Branch02
 ip address 192.168.19.2 255.255.255.240
 no shutdown
 ip access-group SSH in
!
```

## How to run it

```
pip install -r requirements.txt
python3 router_config_push.py
```

The script asks for a username and password at runtime. Set the `NET_USER` environment variable to skip the username prompt. Credentials are never stored in the files.

## What was tested

Validation, rendering and the skipping of disabled devices were tested on lab data, including deliberately broken data (bad IPs, undefined ACL names, invalid actions, a hostname with spaces) to confirm each problem is reported.

The connection and push steps were **not** tested against a live device: without one, the enabled routers end in a timeout. The interface verification was tested against sample `show ip interface brief` text.

## Next steps

- Add a `--dry-run` option that validates and renders without connecting
- Validate subnet masks, not only IP addresses
- Strip comment lines and `end` from the commands before pushing
- Test the push against a lab device
