import getpass
import logging
import time

import yaml

from passlib.hash import sha512_crypt


class MkUser:
    def __init__(self, parent_logger):
        self.logger = parent_logger.getChild(self.__class__.__name__)

        self.userspec_yaml_dict = {"userspec": []}
        self.user_names = []

    def _ask_q(self, query, passwd=False):
        # momentarily replace the streamhandler terminator so that we get rid
        # of the ugly newlines when expecting user input
        logging.StreamHandler.terminator = ""
        self.logger.info("%s: ", query)

        try:
            if passwd:
                response = getpass.getpass(prompt="", stream=None)
            else:
                response = str(input())
        except (EOFError, KeyboardInterrupt):
            print()
            logging.StreamHandler.terminator = "\n"
            self.logger.error("user cancelled the action, exiting")

        logging.StreamHandler.terminator = "\n"

        return response

    def _get_name(self):
        while True:
            name = self._ask_q("input user name")

            if not name:
                self.logger.warning("user name cannot be empty, retry")
                continue

            if " " in name:
                self.logger.warning("user name cannot contain spaces, retry")
                continue

            if name in self.user_names:
                self.logger.warning("user %s is already configured", name)
                continue

            break

        self.user_names.append(name)
        return name

    def _get_passwd(self):
        while True:
            pass1 = self._ask_q("input user password", passwd=True)
            pass2 = self._ask_q("repeat user password", passwd=True)

            if pass1 == pass2:
                if not pass1:
                    self.logger.warning(
                        "empty password provided, disabling password login!"
                    )
                    return

                passwd = sha512_crypt.hash(pass1)
                break

            self.logger.warning("passwords did not match, retry")
            continue

        return passwd

    def _get_ssh_keys(self, passwd):
        ssh_keys, ssh_done = [], False

        while ssh_done is False:
            want_ssh = (
                self._ask_q("do you want to add ssh keys? (y/n)").lower().strip(" ")
            )

            if want_ssh == "y":
                self.logger.info("input ssh keys, provide an empty line when done")

                while True:
                    ask_ssh = self._ask_q("input ssh key")

                    if not ask_ssh:
                        if not ssh_keys:
                            self.logger.warning(
                                "requested auth via ssh keys but no keys were given, retry"
                            )
                            continue
                        break

                    if not ask_ssh:
                        self.logger.warning("ssh key length cannot be 0, retry")
                    else:
                        ssh_keys.append(ask_ssh)
                        passwd = True
                ssh_done = True
            elif want_ssh == "n":
                if not passwd:
                    warn_msg = "user has no password hash or ssh keys added, "
                    warn_msg += "if you do not specify a user-data file that "
                    warn_msg += "contains at least one auth method, you won't "
                    warn_msg += "be able to create a cloud-init ISO."
                else:
                    warn_msg = "user will have passwd auth only"

                self.logger.warning(warn_msg)
                break
            else:
                self.logger.warning("input either `y' or `n'")
                continue

        return list(set(ssh_keys))

    def _get_sudo_god_mode(self):
        while True:
            consent = self._ask_q("do you want sudo god mode? (y/n)").lower().strip(" ")

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
            # UserSpec.name
            user_instance["name"] = self._get_name()

            # UserSpec.password_hash
            user_passwd = self._get_passwd()
            if user_passwd:
                user_instance["password_hash"] = user_passwd

            # UserSpec.ssh_keys
            user_instance["ssh_keys"] = self._get_ssh_keys(passwd=user_passwd)

            # UserSpec.sudo_god_mode
            user_instance["sudo_god_mode"] = self._get_sudo_god_mode()

            # make UserSpec
            self.userspec_yaml_dict["userspec"].append(user_instance)

            # round 2 and onward
            while True:
                want_more_users = self._ask_q("add more users? (y/n)").lower().strip()
                if want_more_users == "y":
                    break

                if want_more_users == "n":
                    users_done = True
                    break

                self.logger.warning("input either `y' or `n'")

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
