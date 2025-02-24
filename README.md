# cloudvirt
cloudvirt creates and destroys `cloud-init` powered x86_64 VMs using the libVirt API.

## installation
### 1. stable
```sh
pip install cloudvirt
```

### 2. dev
```sh
git clone --depth=1 https://github.com/gottaeat/cloudvirt
cd cloudvirt/
pip install .
```

## configuration
### specification
#### domains
| key            | necessity | description                                                                              |
| -------------- | --------- | ---------------------------------------------------------------------------------------- |
| dom_name       | required  | `str` name of the domain                                                                 |
| dom_mem        | required  | `int` amount of memory in megabytes                                                      |
| dom_vcpu       | required  | `int` core count                                                                         |
| net            | required  | `str` name of the libVirt network to associate with the VM                               |
| isolated_port  | optional  | `bool` whether port is isolated. If unset, relevant config not emitted.                  |
| vol_pool       | required  | `str` name of the libVirt pool to associate with the VM                                  |
| vol_size       | required  | `int` disk size in gigabytes                                                             |
| base_image     | optional  | `str` full name of the `cloud-init` capable cloud image[1]                               |
| ip             | check[2]  | `ipv4` ipv4 address or network to be associated with the primary interface of the VM     |
| sshpwauth      | optional  | `bool` whether to allow ssh authentication via passwords (VM-wide, applies to all users) |
| gateway        | check[3]  | `ipv4` the next hop to the default route                                                 |

__[1]__ the cloud image specified must be present in the specified volume pool
and be reachable by libVirt before cloudvirt is executed. if none provided,
`noble-server-cloudimg-amd64.img` is expected to be present.

__[2]__ if specified without a `/`, an attempt at DHCP and DNS reservation will
be made. specifying a `gateway` makes providing a value for this key in CIDR
notation necessary.

if there is no `/`, this address must be within the DHCP range of the libVirt
network specified.

__[3]__ installed as on-link. specifying this makes an `ip` to be supplied in
CIDR notation necessary.

__[2+3]__ these keys must be supplied with a value that abides by the
requirements stated above if the network type for the specified libVirt network
is __not__ one of: `router`, `nat`

#### users
| key           | necessity | description                                                                                            |
| ------------- | --------- | ------------------------------------------------------------------------------------------------------ |
| name          | required  | `str` name of the user                                                                                 |
| password_hash | optional  | `str` password hash in `shadow` compliant `crypt()` format (like `mkuser` output)                      |
| ssh_keys      | optional  | `list of str` list of ssh keys to append to the `authorized_keys` of the user                          |
| sudo_god_mode | required  | `bool` toggle for adding the user to the `sudo` group and allowing it to run `sudo` without a password |

__WARNING__: if you do not specify any authentication method in the file
supplied via `--users` and if you:
1. do not specify an arbitrary `user-data` file via `--userdata`,
2. or, specify a `user-data` but the resulting final `cloud-init` `user-data`
yaml to be written to the iso ends up having no valid authentication method

program will halt.

### examples
#### `--users <userspec.yml>`
you can also do `cloudvirt mkuser` to interactively generate a `userspec.yml`
through prompts.
```yml
---
userspec:
    - name: john
      password_hash: '$y$j9T$/gPg8H0fdtuZh8Ja8decf.$f7IzP89gNaToHUsY2bdgaxv2HJsKSRYLyG6mxNZ6AW3'
      sudo_god_mode: true

    - name: doe
      ssh_keys:
        - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI0000000000000000000000000000000000000000000

```

#### `<vmspec.yml>`
```yml
---
vmspec:
    dom_name: cloudvirttest
    dom_mem: 2048
    dom_vcpu: 2
    net: cloudvirt
#   isolated_port: no
#   ip:
#   gateway:
    vol_pool: cloudvirt
    vol_size: 10
#   base_image:
#   sshpwauth:
```

#### `<pool.xml>`
```xml
<pool type="dir">
  <name>cloudvirt</name>
  <target>
    <path>/pools/cloudvirt</path>
  </target>
</pool>
```
#### `<net.xml>`
```xml
<network>
  <name>cloudvirt</name>
  <forward mode="nat"/>
  <ip address="192.168.253.1" netmask="255.255.255.0">
    <dhcp>
      <range start="192.168.253.1" end="192.168.253.254"/>
    </dhcp>
  </ip>
</network>
```

### usage
```sh
cloudvirt --help
```
