# cloudvirt
cloudvirt creates and destroys cloud-init powered x86_64 VMs using the libVirt
API.

## installation
### release
```sh
pip install cloudvirt
```
### development
```sh
git clone --depth=1 https://github.com/gottaeat/cloudvirt
cd cloudvirt/
pip install .
```
## configuration
### specification
#### domains
| key        | necessity | description                                                                             |
| ---------- | --------- | --------------------------------------------------------------------------------------- |
| dom_name   | required  | `str` name of the domain                                                                |
| dom_mem    | required  | `int` amount of memory in megabytes                                                     |
| dom_vcpu   | required  | `int` core count reserved for the VM                                                    |
| net        | required  | `str` name of the libVirt network to be associated                                      |
| vol_pool   | required  | `str` name of the libVIrt pool to be associated with the VM                             |
| vol_size   | required  | `int` disk size in gigabytes                                                            |
| base_image | optional  | `str` full name of the `cloud-init` capable cloud image[1]                              |
| ip         | check[2]  | `ipv4` ipv4 address or network to be associated with the primary interface of the VM    |
| sshpwauth  | optional  | `bool` whether to allow ssh authentication via passwords VM-wide                        |
| gateway    | check[3]  | `ipv4` the next hop to the default route                                                |

__[1]__ the cloud image must be present in the specified volume pool and be
reachable by libVirt before this program is executed. if none provided,
`noble-server-cloudimg-amd64.img` is expected to be present.

__[2]__ if specified without a forward slash, an attempt at DHCP and DNS
reservation will be made. specifying a `gateway`, makes providing a value for
this key in CIDR notation required. if there is no forward slash, this address
must be within the DHCP range of the libVirt network specified.

__[3]__ installed as on-link. specifying this makes an `ip` to be supplied in
CIDR notation required.

__[2+3]__ these keys must be supplied with a value that abides by the guidelines
stated above if the network type for the specified libVirt network is not one
of: `router`, `nat`

#### users
| key           | necessity | description                                                                         |
| ------------- | --------- | ----------------------------------------------------------------------------------- |
| name          | required  | `str` name of the user                                                              |
| password_hash | optional  | `str` password hash in shadow compliant `crypt()` format (like `mkuser` output)     |
| ssh_keys      | optional  | `list of str` list of ssh keys to appended to the `authorized_keys` of the user     |
| sudo_god_mode | required  | `bool` add user to the `sudo` group and allow user to run `sudo` without a password |

__WARNING__: if you do not specify any authentication method in the userspec:
1. and if you do not specify an arbitrary `user-data` file,
2. and if you specify a `user-data` and the resulting `cloud-init` yaml to be
written to the iso has no valid authentication method

program will halt.

### usage
```sh
cloudvirt --help
```
examples to libVirt volume pools, networks, and VM and user configurations can
be found in the `examples/` directory.
