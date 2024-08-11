import io

import pycdlib
import yaml


# pylint: disable=too-few-public-methods
class CloudInit:
    def __init__(self, vmspec, parent_logger):
        self.vmspec = vmspec
        self.logger = parent_logger.getChild(self.__class__.__name__)

        self.udata = None
        self.mdata = None
        self.netconf = None
        self.iso_path = None

    def _gen_netconf(self):
        self.logger.info("generating network_config")

        base = {}
        base["network"] = {}

        network = base["network"]
        network["version"] = 2
        network["ethernets"] = {}
        network["ethernets"]["id0"] = {}
        network["ethernets"]["id0"]["match"] = {"macaddress": self.vmspec.mac_addr}
        network["ethernets"]["id0"]["addresses"] = [
            f"{self.vmspec.ip}/{self.vmspec.bridge_subnet}"
        ]
        network["ethernets"]["id0"]["nameservers"] = {
            "addresses": ["1.1.1.1", "1.0.0.1"]
        }
        network["ethernets"]["id0"]["routes"] = [
            {
                "to": "0.0.0.0/0",
                "via": self.vmspec.gateway,
                "on-link": True,
            }
        ]

        self.netconf = yaml.dump(base, sort_keys=False).encode("utf-8")

    def _gen_udata(self):
        self.logger.info("generating user-data")

        cloudinit_udata = {}

        if self.vmspec.sshpwauth:
            cloudinit_udata["ssh_pwauth"] = True

        cloudinit_udata["users"] = []
        for userspec in self.vmspec.users:
            user = {
                "name": userspec.name,
                "shell": "/bin/bash",
                "lock_passwd": False,
            }

            if userspec.sudo_god_mode:
                user["groups"] = "sudo"
                user["sudo"] = "ALL=(ALL) NOPASSWD:ALL"

            user["passwd"] = userspec.password_hash

            if userspec.ssh_keys:
                user["ssh_authorized_keys"] = userspec.ssh_keys

            cloudinit_udata["users"].append(user)

        cloud_udata = yaml.dump(
            cloudinit_udata,
            sort_keys=False,
            default_style=None,
        )

        self.udata = f"#cloud-config\n{cloud_udata}".encode("utf-8")

    def _gen_mdata(self):
        self.logger.info("generating meta-data")

        cloudinit_mdata = {
            "instance-id": self.vmspec.dom_name,
            "local-hostname": self.vmspec.dom_name,
        }

        self.mdata = yaml.dump(cloudinit_mdata, sort_keys=False).encode("utf-8")

    def mkiso(self):
        self.logger.info("creating cloud-init ISO")

        # - - init iso - - #
        iso = pycdlib.PyCdlib()
        iso.new(
            interchange_level=4,  # unofficial but same as genisoimage
            joliet=True,
            rock_ridge="1.09",
            vol_ident="CIDATA",
        )

        # - - user data - - #
        self._gen_udata()
        iso.add_fp(
            io.BytesIO(self.udata),
            len(self.udata),
            "/UDATA.;1",
            rr_name="user-data",
            joliet_path="/user-data",
        )

        # - - meta data - - #
        self._gen_mdata()
        iso.add_fp(
            io.BytesIO(self.mdata),
            len(self.mdata),
            "/MDATA.;1",
            rr_name="meta-data",
            joliet_path="/meta-data",
        )

        # - - netplan - - #
        if self.vmspec.ip is not None:
            self._gen_netconf()

            iso.add_fp(
                io.BytesIO(self.netconf),
                len(self.netconf),
                "/NDATA.;1",
                rr_name="network-config",
                joliet_path="/network-config",
            )

        iso.write(self.iso_path)
        iso.close()
