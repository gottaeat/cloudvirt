import logging
import unittest

import yaml

from cloudvirt.spec import UserSpec
from cloudvirt.spec import VMSpec
from cloudvirt.cloudinit import CloudInit
from cloudvirt.log import set_root_logger

set_root_logger(debug=True)
mock_logger = logging.getLogger("cloudvirt")


class CreateCloudInit(unittest.TestCase):
    def test_createcfg(self):
        vmspec = VMSpec()
        testuser = UserSpec()

        testuser.name = "mytestname"
        testuser.password_hash = (
            "$y$j9T$0i28VV.7n07tAyGUHDPzz0$7N1jxo6jUWHafKq1hMX9bvHMq4oIMiu.1v7yv.tB.GD"
        )
        testuser.ssh_keys = ["ssh-lol 123123123"]
        testuser.sudo_god_mode = True

        vmspec.dom_name = "test_dom"
        vmspec.dom_mem = 2
        vmspec.dom_vcpu = 2
        vmspec.net = "test_net"
        vmspec.vol_pool = "test_pool"
        vmspec.vol_size = 25
        vmspec.base_image = "test.img"
        vmspec.vol_name = f"{vmspec.dom_name}-vol.qcow2"
        vmspec.ip = "192.168.254.129"
        vmspec.sshpwauth = True

        vmspec.users.append(testuser)

        cloudinit = CloudInit(vmspec, mock_logger)

        cloud_udata = cloudinit._gen_udata()
        cloud_mdata = cloudinit._gen_mdata()

        udata_parsed = yaml.safe_load(cloudinit.udata)
        mdata_parsed = yaml.safe_load(cloudinit.mdata)

        self.assertEqual(udata_parsed["ssh_pwauth"], True)

        self.assertEqual(1, len(udata_parsed["users"]))

        first_user = udata_parsed["users"][0]

        self.assertEqual(testuser.password_hash, first_user["passwd"])
        self.assertEqual(first_user["groups"], "sudo")
        self.assertEqual(first_user["sudo"], "ALL=(ALL) NOPASSWD:ALL")

        self.assertEqual(first_user["name"], "mytestname")
        self.assertEqual(first_user["shell"], "/bin/bash")
        self.assertEqual(first_user["lock_passwd"], False)
        self.assertEqual(first_user["ssh_authorized_keys"], ["ssh-lol 123123123"])

        self.assertEqual(mdata_parsed["instance-id"], "test_dom")
        self.assertEqual(mdata_parsed["local-hostname"], "test_dom")

    def test_netplancfg(self):
        vmspec = VMSpec()

        testuser = UserSpec()

        testuser.name = "mytestname"
        testuser.password_hash = (
            "$y$j9T$0i28VV.7n07tAyGUHDPzz0$7N1jxo6jUWHafKq1hMX9bvHMq4oIMiu.1v7yv.tB.GD"
        )
        testuser.ssh_key = "ssh-lol 123123123"
        testuser.sudo_god_mode = True

        vmspec.dom_name = "test_dom"
        vmspec.dom_mem = 2
        vmspec.dom_vcpu = 2
        vmspec.net = "test_net"
        vmspec.vol_pool = "test_pool"
        vmspec.vol_size = 25
        vmspec.base_image = "test.img"
        vmspec.vol_name = f"{vmspec.dom_name}-vol.qcow2"
        vmspec.ip = "192.168.254.129"
        vmspec.sshpwauth = True
        vmspec.gateway = "192.168.254.1"
        vmspec.bridge_subnet = "24"
        vmspec.mac_addr = "0a:ba:d1:de:a0:ff"

        vmspec.users.append(testuser)

        cloudinit = CloudInit(vmspec, mock_logger)
        cloudinit.logger = mock_logger

        cloud_netplan = cloudinit._gen_netconf()
        ndata_parsed = yaml.safe_load(cloudinit.netconf)["network"]

        self.assertEqual(2, ndata_parsed["version"])

        netplan_id0 = ndata_parsed["ethernets"]["id0"]
        self.assertEqual(netplan_id0["match"], {"macaddress": "0a:ba:d1:de:a0:ff"})
        self.assertEqual(netplan_id0["addresses"], ["192.168.254.129/24"])
        self.assertEqual(
            netplan_id0["nameservers"], {"addresses": ["1.1.1.1", "1.0.0.1"]}
        )
        self.assertEqual(
            netplan_id0["routes"],
            [{"to": "0.0.0.0/0", "via": "192.168.254.1", "on-link": True}],
        )
