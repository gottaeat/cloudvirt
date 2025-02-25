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
        self.bridge_pfxlen = None
        self.isolated_port = None

        # storage
        self.vol_pool = None
        self.vol_size = None
        self.vol_name = None
        self.base_image = None

        # misc
        self.sshpwauth = None

        # UserSpec
        self.users = []

        # cloud-init user-data
        self.userdata = None


class UserSpec:
    def __init__(self):
        self.name = None
        self.password_hash = None
        self.ssh_keys = []
        self.sudo_god_mode = False
