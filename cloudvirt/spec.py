# pylint: disable=too-many-instance-attributes,too-few-public-methods
class VMSpec:
    def __init__(self):
        # domain
        self.dom_name = None
        self.dom_mem = None
        self.dom_vcpu = None

        # networking
        self.net = None
        self.mac_addr = None
        self.ip = None
        self.gateway = None
        self.bridge_subnet = None

        # storage
        self.vol_pool = None
        self.vol_size = None
        self.vol_name = None
        self.base_image = None

        # misc
        self.sshpwauth = False

        # UserSpec
        self.users = []


# pylint: disable=too-few-public-methods
class UserSpec:
    def __init__(self):
        self.name = None
        self.password_hash = None
        self.ssh_keys = []
        self.sudo_god_mode = False
