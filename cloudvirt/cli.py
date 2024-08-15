import argparse
import logging

from .config import ConfigYAML
from .driver import APIDriver
from .log import set_root_logger
from .mkuser import MkUser
from .util import ask_q

from . import __version__ as pkg_version


class CLI:
    def __init__(self):
        self.logger = None

        self.args = None
        self.subparsers = None

        self.driver = None

    # - - parsing - - #
    def _mkuser_args(self):
        mkuser_subparser_desc = "create a UserSpec yaml to be consumed by --userspec"

        self.subparsers.add_parser(
            "mkuser", help=mkuser_subparser_desc, description=mkuser_subparser_desc
        )

    def _nuke_args(self):
        nuke_subparser_desc = "nuke a vm"
        nuke_subparser_name_help = "name of the domain to be nuked"
        nuke_subparser_noconfirm_help = "skip the confirmation dialogue"

        nuke_subparser = self.subparsers.add_parser(
            "nuke", help=nuke_subparser_desc, description=nuke_subparser_desc
        )
        nuke_subparser.add_argument("name", type=str, help=nuke_subparser_name_help)
        nuke_subparser.add_argument(
            "--noconfirm",
            action="store_true",
            required=False,
            help=nuke_subparser_noconfirm_help,
        )

    def _create_args(self):
        create_subparser_desc = "create a vm"
        create_subparser_vmspec_help = "yaml file holding the vm config"
        create_subparser_userspec_help = "yaml file holding the user config"
        create_subparser_userdata_help = "cloud-init user-data file"

        create_subparser = self.subparsers.add_parser(
            "create", help=create_subparser_desc, description=create_subparser_desc
        )

        create_subparser.add_argument(
            "vmspec_file",
            help=create_subparser_vmspec_help,
        )

        create_subparser.add_argument(
            "--userdata",
            dest="userdata_file",
            required=False,
            help=create_subparser_userdata_help,
        )

        create_subparser.add_argument(
            "--users",
            dest="userspec_file",
            required=False,
            help=create_subparser_userspec_help,
        )

    def _gen_args(self):
        parser_desc = f"cloudvirt VM orchestrator ver. {pkg_version}"
        parser_d_help = "enable debugging"

        parser = argparse.ArgumentParser(description=parser_desc)
        parser.add_argument("-d", dest="debug", action="store_true", help=parser_d_help)

        self.subparsers = parser.add_subparsers(dest="command", required=True)

        self._create_args()
        self._nuke_args()
        self._mkuser_args()
        self.args = parser.parse_args()

    # - - driver actions - - #
    def _nuke(self):
        if self.args.noconfirm:
            want_nuke = True
        else:
            while True:
                consent = (
                    ask_q(f"do you want {self.args.name} nuked? (y/n)")
                    .lower()
                    .strip(" ")
                )

                want_nuke = (
                    True if consent == "y" else False if consent == "n" else None
                )

                if want_nuke is None:
                    self.logger.warning("input either `y' or `n'.")
                else:
                    break

        if want_nuke:
            self.driver.nuke(self.args.name)
        else:
            self.logger.warning("user cancelled action, bailing out.")

    def _create(self):
        config = ConfigYAML(
            self.args.vmspec_file,
            self.args.userspec_file,
            self.args.userdata_file,
        )
        config.run()

        if not self.args.userspec_file and not self.args.userdata_file:
            err_msg = "no users or user-data file was provided, bailing out as "
            err_msg += "you may be unable to log in to an VMs created"
            self.logger.error(err_msg)

        self.driver.create(config.vmspec)

    # - - main - - #
    def run(self):
        self._gen_args()

        set_root_logger(self.args.debug)
        self.logger = logging.getLogger(self.__class__.__name__)

        self.logger.info("started cloudvirt ver. %s", pkg_version)

        # - - mkuser - - #
        if self.args.command == "mkuser":
            mku = MkUser()
            return mku.run()

        # - - driver action - - #
        self.driver = APIDriver()
        self.driver.connect()

        if self.args.command == "create":
            self._create()
        elif self.args.command == "nuke":
            self._nuke()

        self.logger.info("closing connection to the libVirt API")
        self.driver.close()


def run():
    c = CLI()
    c.run()
