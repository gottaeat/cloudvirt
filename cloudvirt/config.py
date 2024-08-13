import ipaddress
import os

import yaml

from .spec import VMSpec, UserSpec


# pylint: disable=too-few-public-methods
class ConfigYAML:
    def __init__(self, vmspec_file, userspec_file, userdata_file, parent_logger):
        self.vmspec_file = vmspec_file
        self.userspec_file = userspec_file
        self.userdata_file = userdata_file
        self.logger = parent_logger.getChild(self.__class__.__name__)

        self.vmspec = None

    # pylint: disable=too-many-branches,too-many-statements
    def _parse_vmspec(self):
        # - - load yaml - - #
        self.logger.info("loading VMSpec() yaml")

        if os.path.isfile(self.vmspec_file):
            try:
                with open(self.vmspec_file, "r", encoding="utf-8") as yaml_file:
                    yaml_parsed = yaml.load(yaml_file.read(), Loader=yaml.Loader)
            # pylint: disable=bare-except
            except:
                self.logger.exception("%s parsing has failed", self.vmspec_file)
        else:
            self.logger.error("%s is not a file", self.vmspec_file)

        # - - parse yaml - - #
        self.logger.info("parsing VMSpec() yaml")

        # fmt: off
        try:
            vmspec_yaml = yaml_parsed[ # pylint: disable=possibly-used-before-assignment
                "vmspec"
            ]
        except KeyError:
            self.logger.exception("vmspec section in the YAML file is missing")

        vmspec_must_have = [
            "dom_name",
            "dom_mem",
            "dom_vcpu",
            "net",
            "vol_pool",
            "vol_size",
        ]
        # fmt: on

        for item in vmspec_must_have:
            if item not in vmspec_yaml.keys():
                self.logger.error("%s is missing from the YAML", item)
            if not vmspec_yaml[item]:
                self.logger.error("%s cannot be blank", item)

        # - - generate vmspec - - #
        self.logger.info("creating VMSpec() for: %s", vmspec_yaml["dom_name"])

        self.vmspec = VMSpec()

        # vmspec.dom_name
        self.vmspec.dom_name = str(vmspec_yaml["dom_name"])

        # vmspec.dom_mem
        self.vmspec.dom_mem = int(vmspec_yaml["dom_mem"])

        # vmspec.dom_vcpu
        self.vmspec.dom_vcpu = int(vmspec_yaml["dom_vcpu"])

        # vmspec.net
        self.vmspec.net = str(vmspec_yaml["net"])

        # vmspec.vol_pool
        self.vmspec.vol_pool = str(vmspec_yaml["vol_pool"])

        # vmspec.vol_size
        self.vmspec.vol_size = int(vmspec_yaml["vol_size"])

        # vmspec.vol_name
        self.vmspec.vol_name = f"{self.vmspec.dom_name}-vol.qcow2"

        # vmspec.base_image
        try:
            if vmspec_yaml["base_image"] is None:
                self.logger.error("base_image cannot be specified then left blank")
            else:
                self.vmspec.base_image = str(vmspec_yaml["base_image"])
        except KeyError:
            self.vmspec.base_image = "noble-server-cloudimg-amd64.img"

        # vmspec.ip
        try:
            if vmspec_yaml["ip"] is None:
                self.logger.error("ip cannot be specified then left blank")
            else:
                self.vmspec.ip = str(vmspec_yaml["ip"])

        except KeyError:
            pass

        if self.vmspec.ip:
            try:
                if "/" in self.vmspec.ip:
                    ipaddress.ip_network(self.vmspec.ip)
                else:
                    ipaddress.ip_address(self.vmspec.ip)
            except ValueError:
                self.logger.exception("%s is not a valid ipv4 address.", self.vmspec.ip)

            ip_parts = self.vmspec.ip.split("/")
            self.vmspec.ip = ip_parts[0]

            if len(ip_parts) == 2:
                self.vmspec.bridge_subnet = ip_parts[1]

        # vmspec.sshpwauth
        try:
            if vmspec_yaml["sshpwauth"] is None:
                self.logger.error("sshpwauth cannot be specified then left blank")

            if type(vmspec_yaml["sshpwauth"]).__name__ != "bool":
                self.logger.error("sshpwauth should be a bool.")

            self.vmspec.sshpwauth = vmspec_yaml["sshpwauth"]
        except KeyError:
            pass

        # vmspec.gateway
        try:
            if vmspec_yaml["gateway"] is None:
                self.logger.error("gateway cannot be specified then left blank")

            self.vmspec.gateway = vmspec_yaml["gateway"]
        except KeyError:
            pass

    def _parse_userspec(self):
        # - - load yaml - - #
        if not self.userspec_file:
            return self.logger.info("no userspec configuration was provided")

        self.logger.info("loading UserSpec() yaml")

        if os.path.isfile(self.userspec_file):
            try:
                with open(self.userspec_file, "r", encoding="utf-8") as yaml_file:
                    yaml_parsed = yaml.load(yaml_file.read(), Loader=yaml.Loader)
            # pylint: disable=bare-except
            except:
                self.logger.exception("%s parsing has failed", self.userspec_file)
        else:
            self.logger.error("%s is not a file", self.userspec_file)

        # - - parse yaml - - #
        self.logger.info("parsing UserSpec() yaml")

        try:
            userspec_yaml = (
                yaml_parsed[  # pylint: disable=possibly-used-before-assignment
                    "userspec"
                ]
            )
        except KeyError:
            self.logger.exception("userspec section in the YAML file is missing")

        userspec_must_have = ["name", "password_hash"]

        for user in userspec_yaml:
            for item in userspec_must_have:
                if item not in user.keys():
                    self.logger.error("%s is missing from the YAML", item)
                if not user[item]:
                    self.logger.error("%s cannot be blank", item)

            # - - create userspec - - #
            self.logger.info("creating UserSpec() for: %s", user["name"])

            userspec = UserSpec()

            # userspec.name
            userspec.name = str(user["name"])

            # userspec.password_hash
            userspec.password_hash = str(user["password_hash"])

            # userspec.ssh_keys
            try:
                for key in user["ssh_keys"]:
                    if key is None:
                        self.logger.error(
                            "ssh_keys cannot be specified then contain empty elements"
                        )

                    userspec.ssh_keys.append(str(key))
            except TypeError:
                self.logger.exception(
                    "ssh_keys cannot be specified and have no elements"
                )
            except KeyError:
                pass

            # userspec.sudo_god_mode
            try:
                if user["sudo_god_mode"] is None:
                    self.logger.error(
                        "sudo_god_mode cannot be specified then left blank"
                    )

                if type(user["sudo_god_mode"]).__name__ != "bool":
                    self.logger.error("sudo_god_mode should be a bool.")

                userspec.sudo_god_mode = user["sudo_god_mode"]
            except KeyError:
                pass

            self.vmspec.users.append(userspec)

    def _parse_userdata(self):
        # - - load yaml - - #
        if not self.userdata_file:
            return self.logger.info("no arbitrary user-data was provided")

        self.logger.info("loading UserSpec() yaml")

        if os.path.isfile(self.userdata_file):
            try:
                with open(self.userdata_file, "r", encoding="utf-8") as yaml_file:
                    yaml_parsed = yaml.load(yaml_file.read(), Loader=yaml.Loader)
            # pylint: disable=bare-except
            except:
                self.logger.exception("%s parsing has failed", self.userdata_file)
        else:
            self.logger.error("%s is not a file", self.userdata_file)

        self.vmspec.userdata = (
            yaml_parsed  # pylint: disable=possibly-used-before-assignment
        )

    def run(self):
        self._parse_vmspec()
        self._parse_userspec()
        self._parse_userdata()
