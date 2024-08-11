import argparse
import logging

from .config import ConfigYAML
from .driver import APIDriver
from .log import set_root_logger
from .mkuser import MkUser

from . import __version__ as pkg_version


# pylint: disable=too-few-public-methods
class CLI:
    def __init__(self):
        self.logger = None

        self.args = None
        self.subparsers = None

        self.driver = None

    # - - parsing - - #
    def _mkuser_args(self):
        mkuser_subparser_desc = "Create a UserSpec YAML!"
        mkuser_subparser_help = "Create a UserSpec YAML!"

        self.subparsers.add_parser(
            "mkuser", help=mkuser_subparser_help, description=mkuser_subparser_desc
        )

    def _nuke_args(self):
        nuke_subparser_desc = "Nuke a VM!"
        nuke_subparser_help = "Nuke a VM!"
        nuke_subparser_name_help = "Name of the domain to be nuked."
        nuke_subparser_noconfirm_help = "Skip the confirmation prompt."

        nuke_subparser = self.subparsers.add_parser(
            "nuke", help=nuke_subparser_help, description=nuke_subparser_desc
        )
        nuke_subparser.add_argument("name", type=str, help=nuke_subparser_name_help)
        nuke_subparser.add_argument(
            "--noconfirm",
            action="store_true",
            required=False,
            help=nuke_subparser_noconfirm_help,
        )

    def _create_args(self):
        create_subparser_desc = "Create a VM!"
        create_subparser_help = "Create a VM!"
        create_subparser_vmspec_help = "VM specification YAML file."
        create_subparser_userspec_help = "User(s) specification YAML file."

        create_subparser = self.subparsers.add_parser(
            "create", help=create_subparser_help, description=create_subparser_desc
        )

        create_subparser.add_argument(
            "--vmspec",
            dest="vmspec_file",
            required=True,
            help=create_subparser_vmspec_help,
        )

        create_subparser.add_argument(
            "--userspec",
            dest="userspec_file",
            required=True,
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
                self.logger.info("do you want %s nuked? (y/n): ", self.args.name)
                consent = str(input().lower().strip(" "))

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

    # pylint: disable=too-many-statements
    def _create(self):
        config = ConfigYAML(self.args.vmspec_file, self.args.userspec_file, self.logger)
        config.parse_yaml()

        self.driver.create(config.vmspec)

    # - - main - - #
    def run(self):  # pylint: disable=inconsistent-return-statements
        self._gen_args()

        set_root_logger(self.args.debug)
        self.logger = logging.getLogger("cloudvirt")

        self.logger.info("started cloudvirt ver. %s", pkg_version)

        # - - mkuser - - #
        if self.args.command == "mkuser":
            mku = MkUser(self.logger)
            return mku.run()

        # - - driver action - - #
        self.driver = APIDriver(self.logger)
        self.driver.connect()

        if self.args.command == "create":
            self._create()
        elif self.args.command == "nuke":
            self._nuke()

        self.logger.info("closing connection to the libVirt API")
        self.driver.close()


def run():
    # pylint: disable=invalid-name
    c = CLI()
    c.run()
