import getpass
import time

import yaml

from passlib.hash import sha512_crypt


# pylint: disable=too-few-public-methods
class MkUser:
    def __init__(self, parent_logger):
        self.logger = parent_logger.getChild(self.__class__.__name__)

        self.userspec_yaml_dict = {"userspec": []}

    def _get_name(self):
        while True:
            self.logger.info("input user name:")
            name = str(input())

            if len(name) == 0:
                self.logger.warning("user name cannot be empty, retry")
                continue

            if " " in name:
                self.logger.warning("user name cannot contain spaces, retry")
                continue

            break

        return name

    def _get_passwd(self):
        while True:
            self.logger.info("input user password:")
            pass1 = getpass.getpass(prompt="", stream=None)

            self.logger.info("repeat user password:")
            pass2 = getpass.getpass(prompt="", stream=None)

            if pass1 == pass2:
                passwd = sha512_crypt.hash(pass1)
                break

            self.logger.warning("passwords did not match, retry")
            continue

        return passwd

    def _get_ssh_keys(self):
        ssh_keys, ssh_done = [], False

        while ssh_done is False:
            self.logger.info("do you want to add ssh keys? (y/n):")
            want_ssh = str(input().lower().strip(" "))

            if want_ssh == "y":
                self.logger.info("input ssh keys, type `done' when done")

                while True:
                    self.logger.info("input ssh key:")
                    ask_ssh = str(input())

                    if ask_ssh == "done":
                        if len(ssh_keys) == 0:
                            warn_msg = "requested ssh key auth, but no keys "
                            warn_msg += "were given, retry"

                            self.logger.warning(warn_msg)

                            continue

                        break

                    if len(ask_ssh) == 0:
                        self.logger.warning("ssh key length cannot be 0, retry")
                    else:
                        ssh_keys.append(ask_ssh)
                ssh_done = True
            elif want_ssh == "n":
                self.logger.info("user will have passwd auth only")
                break
            else:
                self.logger.info("input either `y' or `n'")
                continue

        return ssh_keys

    def _get_sudo_god_mode(self):
        while True:
            self.logger.info("do you want sudo god mode? (y/n): ")
            consent = str(input().lower().strip(" "))

            sudo_god_mode = (
                True if consent == "y" else False if consent == "n" else None
            )

            if sudo_god_mode is None:
                self.logger.warning("input either `y' or `n'.")
            else:
                break

        return sudo_god_mode

    def _collect_users(self):
        users_done = False
        while users_done is False:
            user_instance = {}
            user_instance["name"] = self._get_name()
            user_instance["password_hash"] = self._get_passwd()
            user_instance["ssh_keys"] = self._get_ssh_keys()
            user_instance["sudo_god_mode"] = self._get_sudo_god_mode()

            self.userspec_yaml_dict["userspec"].append(user_instance)

            # round 2 and onward
            self.logger.info("add more users? (y/n):")
            want_more_users = str(input()).lower().strip(" ")

            if want_more_users == "y":
                continue

            if want_more_users == "n":
                users_done = True
            else:
                self.logger.warning("input either `y' or `n'")
                continue

    def _dump_yaml(self):
        yaml_str = yaml.dump(self.userspec_yaml_dict, sort_keys=False)
        yaml_filename = f"{time.strftime('userspec-%Y%m%d_%H%M%S')}.yml"

        self.logger.info(
            "saving userspec to the current directory as: %s", yaml_filename
        )

        with open(f"./{yaml_filename}", "w", encoding="utf-8") as yaml_file:
            yaml_file.write(yaml_str)

    def run(self):
        self._collect_users()
        self._dump_yaml()
