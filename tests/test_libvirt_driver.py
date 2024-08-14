import logging
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

import libvirt

from cloudvirt.driver import APIDriverVMCreator
from cloudvirt.driver import APIDriverVMNuker
from cloudvirt.log import set_root_logger
from cloudvirt.spec import VMSpec, UserSpec

set_root_logger(debug=True)
mock_logger = logging.getLogger("cloudvirt")


def get_testfile(name):
    return os.path.join(os.path.dirname(__file__), name)


class MockStorageVol:
    def delete(self):
        return None


class MockDirStoragePool:
    def __init__(self, name, path):
        self.name = name
        self.path = path

    def XMLDesc(self):
        xml = f"""
            <pool type='dir'>
              <name>{self.name}</name>
              <uuid>ac3311e0-4886-45e4-8134-8428a594547b</uuid>
              <capacity unit='bytes'>527298895872</capacity>
              <allocation unit='bytes'>91432857600</allocation>
              <available unit='bytes'>435866038272</available>
              <source>
              </source>
              <target>
                <path>{self.path}</path>
                <permissions>
                  <mode>0755</mode>
                  <owner>1000</owner>
                  <group>1000</group>
                </permissions>
              </target>
            </pool>
        """
        return xml

    def createXML(self, xml, weird_number):
        if weird_number != 0:
            raise ValueError("what the fuck weird number did you pass?")

    def refresh(self):
        return 0

    def storageVolLookupByName(self, name):
        return MockStorageVol()


class MockNetwork:
    def __init__(self, name, dhcp_start="192.168.254.128", dhcp_end="192.168.254.254"):
        self.name = name
        self.dhcp_start = dhcp_start
        self.dhcp_end = dhcp_end

    def XMLDesc(self):
        xml = f"""
            <network>
              <name>{self.name}</name>
              <uuid>803cb35a-75e9-451f-97d2-9b758b0102ef</uuid>
              <forward mode='nat'>
                <nat>
                  <port start='1024' end='65535'/>
                </nat>
              </forward>
              <bridge name='virbr1' stp='on' delay='0'/>
              <mac address='52:54:00:87:8f:71'/>
              <domain name='cloudvirt-net'/>
              <ip address='192.168.254.1' netmask='255.255.255.0'>
                <dhcp>
                  <range start="{self.dhcp_start}" end="{self.dhcp_end}"/>
                </dhcp>
              </ip>
            </network>
        """

        return xml

    def DHCPLeases(self, mac=None, flags=0):
        return []

    def update(self, command, section, parentIndex, xml, flags=0):
        return None


class MockDom:
    def __init__(self, xml=None):
        self.xml = xml

    def create(self):
        pass

    def XMLDesc(self):
        if self.xml:
            return self.xml

        domxml_path = get_testfile("realdom.xml")

        domxml = None
        with open(domxml_path, "r") as f:
            domxml = f.read()

        return domxml

    def isActive(self):
        # lol this is probably a stupid idea i will forget about
        return 1

    def interfaceAddresses(self, src):
        if src == libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE:
            return {}
        elif src == libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_ARP:
            return {
                "vnet0": {
                    "addrs": [{"addr": "192.168.254.131", "prefix": 0, "type": 0}],
                    "hwaddr": "52:54:60:38:67:43",
                }
            }

    def destroy(self):
        return 0

    def undefine(self):
        return 0


class MockDriver:
    def __init__(self, pool_path, parent_logger):
        self.pool_path = pool_path
        self.logger = parent_logger.getChild(self.__class__.__name__)

        self._known_doms = {"test_nuke_dom": MockDom()}

    def networkLookupByName(self, name):
        return MockNetwork(name)

    def storagePoolLookupByName(self, name):
        return MockDirStoragePool("test_pool", self.pool_path)

    def defineXML(self, xml):
        dom_xml = ET.ElementTree(ET.fromstring(xml))
        dom_root = dom_xml.getroot()
        name = dom_root.findall("name")[0].text
        self._known_doms[name] = MockDom(xml)

    def lookupByName(self, name):
        if name == "existing_dom":
            raise libvirt.libvirtError("already exists!")

        if name in self._known_doms:
            return self._known_doms[name]
        else:
            raise libvirt.libvirtError("Nothing found baybe!!")


class NukeVM(unittest.TestCase):
    def test_nukevm(self):
        driver = MockDriver(None, mock_logger)

        vmspec = VMSpec()
        vmspec.dom_name = "test_nuke_dom"
        vmspec.dom_mem = 2
        vmspec.dom_vcpu = 2
        vmspec.net = "test_net"
        vmspec.vol_pool = "test_pool"
        vmspec.vol_size = 25
        vmspec.base_image = "test.img"
        vmspec.vol_name = f"{vmspec.dom_name}-vol.qcow2"
        vmspec.ip = "192.168.254.129"
        vmspec.sshpwauth = True

        testuser = UserSpec()
        testuser.name = "mytestname"
        testuser.password_hash = (
            "$y$j9T$0i28VV.7n07tAyGUHDPzz0$7N1jxo6jUWHafKq1hMX9bvHMq4oIMiu.1v7yv.tB.GD"
        )
        vmspec.users.append(testuser)

        c = APIDriverVMNuker(driver, vmspec.dom_name, driver.logger)
        c.nuke()

    def test_nonexistant_dom_name(self):
        driver = MockDriver(None, mock_logger)

        vmspec = VMSpec()
        vmspec.dom_name = "nonexistant_dom"
        vmspec.sshpwauth = True

        testuser = UserSpec()
        testuser.name = "mytestname"
        testuser.password_hash = (
            "$y$j9T$0i28VV.7n07tAyGUHDPzz0$7N1jxo6jUWHafKq1hMX9bvHMq4oIMiu.1v7yv.tB.GD"
        )
        vmspec.users.append(testuser)

        c = APIDriverVMNuker(driver, vmspec.dom_name, driver.logger)

        # normally would catch libvirt.libvirtError but our logger exits with 1
        # when exception/error is called, so catch that.
        with self.assertRaises(SystemExit):
            c.nuke()


class CreateVM(unittest.TestCase):
    def setUp(self):
        self.vol_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.vol_dir.cleanup()

    def test_createvm(self):
        driver = MockDriver(self.vol_dir.name, mock_logger)

        vmspec = VMSpec()
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

        testuser = UserSpec()
        testuser.name = "mytestname"
        testuser.password_hash = (
            "$y$j9T$0i28VV.7n07tAyGUHDPzz0$7N1jxo6jUWHafKq1hMX9bvHMq4oIMiu.1v7yv.tB.GD"
        )
        vmspec.users.append(testuser)

        c = APIDriverVMCreator(driver, vmspec, driver.logger)
        c.create()

    def test_existing_dom_name(self):
        driver = MockDriver(self.vol_dir.name, mock_logger)

        vmspec = VMSpec()
        vmspec.dom_name = "existing_dom"
        vmspec.dom_mem = 2
        vmspec.dom_vcpu = 2
        vmspec.net = "test_net"
        vmspec.vol_pool = "test_pool"
        vmspec.vol_size = 25
        vmspec.base_image = "test.img"
        vmspec.vol_name = f"{vmspec.dom_name}-vol.qcow2"
        vmspec.ip = "192.168.254.129"
        vmspec.sshpwauth = True

        testuser = UserSpec()
        testuser.name = "mytestname"
        testuser.password_hash = (
            "$y$j9T$0i28VV.7n07tAyGUHDPzz0$7N1jxo6jUWHafKq1hMX9bvHMq4oIMiu.1v7yv.tB.GD"
        )
        vmspec.users.append(testuser)

        c = APIDriverVMCreator(driver, vmspec, driver.logger)

        with self.assertRaises(libvirt.libvirtError):
            c.create()
