import io
import logging

import pycdlib
import yaml


class CloudInit:
    def __init__(self, vmspec):
        self.vmspec = vmspec

        self.logger = logging.getLogger(self.__class__.__name__)

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
            f"{self.vmspec.ip}/{self.vmspec.bridge_pfxlen}"
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
        # generate user-data
        self.logger.info("generating user-data")

        # init dict if no user-data
        cloudinit_udata = self.vmspec.userdata if self.vmspec.userdata else {}

        # user-data.ssh_pwauth (bool)
        if self.vmspec.sshpwauth is not None:
            # check for collission between VMSpec().sshpwauth and
            # user-data.ssh_pwauth
            if (
                "ssh_pwauth" in cloudinit_udata
                and self.vmspec.sshpwauth != cloudinit_udata["ssh_pwauth"]
            ):
                self.logger.error(
                    'user-data has "ssh_pwauth" set to %s while the vmspec value is %s',
                    cloudinit_udata["ssh_pwauth"],
                    self.vmspec.sshpwauth,
                )

            # override
            cloudinit_udata["ssh_pwauth"] = self.vmspec.sshpwauth

        # user-data.users (list)
        if "users" not in cloudinit_udata:
            cloudinit_udata["users"] = []

        for userspec in self.vmspec.users:
            # get handle to the matching user in the user-data
            user_dict = next(
                (
                    user
                    for user in cloudinit_udata["users"]
                    if user["name"] == userspec.name
                ),
                None,
            )

            # check if a matching user was found, if not, init it with its name
            if not user_dict:
                user_dict = {"name": userspec.name}
                cloudinit_udata["users"].append(user_dict)

            # force replace our defaults
            user_dict["shell"] = "/bin/bash"  # only shell that matters
            user_dict["lock_passwd"] = False  # allow console login in all cases

            # sudo
            if userspec.sudo_god_mode:
                if "groups" in user_dict:
                    # convert existing groups to list if str
                    if isinstance(user_dict["groups"], str):
                        user_dict["groups"] = [user_dict["groups"]]
                else:
                    user_dict["groups"] = []

                # add sudo to groups
                if "sudo" not in user_dict["groups"]:
                    user_dict["groups"].append("sudo")

                # convert existing sudo values to list if str
                if "sudo" in user_dict:
                    if isinstance(user_dict["sudo"], str):
                        user_dict["sudo"] = [user_dict["sudo"]]
                else:
                    # init if not present
                    user_dict["sudo"] = []

                # enable god mode
                user_dict["sudo"] = list(
                    set(user_dict["sudo"] + ["ALL=(ALL) NOPASSWD:ALL"])
                )

            # force userspec provided pass
            if userspec.password_hash:
                user_dict["passwd"] = userspec.password_hash

            # append ssh keys
            if userspec.ssh_keys:
                if "ssh_authorized_keys" in user_dict:
                    if isinstance(user_dict["ssh_authorized_keys"], str):
                        user_dict["ssh_authorized_keys"] = [
                            user_dict["ssh_authorized_keys"]
                        ]
                else:
                    user_dict["ssh_authorized_keys"] = []

                for key in userspec.ssh_keys:
                    user_dict["ssh_authorized_keys"] = list(
                        dict.fromkeys(user_dict["ssh_authorized_keys"] + [key])
                    )

            if "ssh_authorized_keys" in user_dict:
                # remove empty items from list
                user_dict["ssh_authorized_keys"] = [
                    x for x in user_dict["ssh_authorized_keys"] if x != ""
                ]

                # check if anything remains
                if not user_dict["ssh_authorized_keys"]:
                    self.logger.error(
                        "resulting ssh_authorized_keys for %s does not contain any keys",
                        user_dict["name"],
                    )
            else:
                # no passwd, no ssh keys == no auth
                if "passwd" not in user_dict:
                    self.logger.error(
                        "user %s does not have a passwd or a ssh key", user_dict["name"]
                    )
                else:
                    if (
                        "ssh_pwauth" not in cloudinit_udata
                        or not cloudinit_udata["ssh_pwauth"]
                    ):
                        err_msg = f"user {user_dict['name']} only has passwd "
                        err_msg += "for auth but the ssh_pwauth is not defined "
                        err_msg += "or set to false"
                        self.logger.error(err_msg)

        if not cloudinit_udata["users"]:
            self.logger.error("resulting user-data contains no users")

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
