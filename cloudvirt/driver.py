import grp
import ipaddress
import logging
import os
import pwd
import random
import xml.etree.ElementTree as ET

from functools import wraps

import libvirt

from .cloudinit import CloudInit


class APIDriverVMNuker:
    def __init__(self, driver, dom_name):
        self.driver = driver
        self.dom_name = dom_name

        self.logger = logging.getLogger(self.__class__.__name__)

        self._dom = None
        self._domxml_root = None

    def _dom_exists_precheck(self):
        try:
            self.driver.lookupByName(self.dom_name)
        except libvirt.libvirtError:
            self.logger.error("domain %s does not exist.", self.dom_name)

    def _get_dom_xml(self):
        self.logger.info("getting domain XML")

        self._dom = self.driver.lookupByName(self.dom_name)

        dom_xml = self._dom.XMLDesc()
        domxml_tree = ET.ElementTree(ET.fromstring(dom_xml))
        self._domxml_root = domxml_tree.getroot()

    def _nuke_dns_entries(self, network, netxml_root):
        for hostname in netxml_root.findall("dns/host/hostname"):
            if hostname.text == self.dom_name:
                self.logger.info("nuking DNS entried")

                dnsupdxml_root = ET.Element("host")
                ET.SubElement(dnsupdxml_root, "hostname").text = self.dom_name
                dnsupdxml = ET.tostring(dnsupdxml_root, encoding="unicode")

                network.update(
                    libvirt.VIR_NETWORK_UPDATE_COMMAND_DELETE,
                    libvirt.VIR_NETWORK_SECTION_DNS_HOST,
                    -1,
                    dnsupdxml,
                    libvirt.VIR_NETWORK_UPDATE_AFFECT_LIVE
                    | libvirt.VIR_NETWORK_UPDATE_AFFECT_CONFIG,
                )

    def _nuke_dhcp_entries(self, network, netxml_root):
        for res in netxml_root.findall("ip/dhcp/host"):
            if res.attrib["name"] == self.dom_name:
                self.logger.info("nuking DHCP entries")

                netupdxml_root = ET.Element("host", {"name": self.dom_name})
                netupdxml = ET.tostring(netupdxml_root, encoding="unicode")

                network.update(
                    libvirt.VIR_NETWORK_UPDATE_COMMAND_DELETE,
                    libvirt.VIR_NETWORK_SECTION_IP_DHCP_HOST,
                    -1,
                    netupdxml,
                    libvirt.VIR_NETWORK_UPDATE_AFFECT_LIVE
                    | libvirt.VIR_NETWORK_UPDATE_AFFECT_CONFIG,
                )

    def _nuke_net_entries(self):
        dom_net = self._domxml_root.findall("devices/interface/source")[0].attrib[
            "network"
        ]

        network = self.driver.networkLookupByName(dom_net)
        network_xml = network.XMLDesc()
        netxml_tree = ET.ElementTree(ET.fromstring(network_xml))
        netxml_root = netxml_tree.getroot()

        network_type = netxml_root.find("forward")
        if "mode" not in network_type.attrib or network_type.attrib["mode"] not in [
            "route",
            "open",
            "nat",
        ]:
            return

        self._nuke_dns_entries(network, netxml_root)
        self._nuke_dhcp_entries(network, netxml_root)

    def _nuke_vm(self):
        if self._dom.isActive():
            self.logger.info("stopping domain")
            self._dom.destroy()

        self.logger.info("nuking domain")
        self._dom.undefine()

    def _nuke_volumes(self):
        self.logger.info("nuking associated volumes")

        dom_disks = self._domxml_root.findall("devices/disk/source")
        for source in enumerate(dom_disks):
            disk = dom_disks[source[0]].attrib
            pool = self.driver.storagePoolLookupByName(disk["pool"])
            vol = pool.storageVolLookupByName(disk["volume"])
            vol.delete()

    def nuke(self):
        self.logger.info("nuking VM: %s", self.dom_name)
        self._dom_exists_precheck()
        self._get_dom_xml()
        self._nuke_net_entries()
        self._nuke_vm()
        self._nuke_volumes()


class APIDriverVMCreator:
    def __init__(self, driver, vmspec):
        self.driver = driver
        self.vmspec = vmspec

        self.logger = logging.getLogger(self.__class__.__name__)

        self._pool_path = None
        self._pool = None
        self._cloudinit_iso = None
        self._network = None

    def _genmac(self):
        self.logger.info("generating mac address")

        i, vmmac = 0, "52:54:"
        while i < 4:
            col = hex(random.randint(0, 255)).lstrip("0x")
            if len(col) < 2:
                col = f"{col}0"
            vmmac += f"{col}:"

            i += 1

        return str(vmmac.rstrip(":"))

    def _dom_exists_precheck(self):
        try:
            self.driver.lookupByName(self.vmspec.dom_name)
        except libvirt.libvirtError:
            pass
        else:
            self.logger.error("domain %s already exists", self.vmspec.dom_name)

    def _network_precheck(self):
        self.logger.info("starting network pre-checks")

        needs_net_update = False
        network = self.driver.networkLookupByName(self.vmspec.net)
        self._network = network

        network_xml = network.XMLDesc()
        netxml_tree = ET.ElementTree(ET.fromstring(network_xml))
        netxml_root = netxml_tree.getroot()

        network_type = netxml_root.find("forward")

        if network_type is None:
            self.logger.error("%s does not have a `forward' element.", self.vmspec.net)

        if "mode" not in network_type.attrib or network_type.attrib["mode"] not in [
            "route",
            "open",
            "nat",
        ]:
            self.logger.info("prechecks are not used for the route and nat modes")

            if self.vmspec.gateway is None:
                self.logger.error("driver cannot derive the gateway")

            if self.vmspec.bridge_pfxlen is None:
                self.logger.error("ip needs to be in CIDR notation")

            return needs_net_update

        # static ip sanity checks. Only for NAT and routed
        if self.vmspec.ip is not None:
            needs_net_update = True

            # check if already leased or reserved
            active_leases = []
            for lease in network.DHCPLeases():
                active_leases.append(lease["ipaddr"])

            if self.vmspec.ip in active_leases:
                self.logger.error(
                    "%s is already leased in %s", self.vmspec.ip, self.vmspec.net
                )

            reserved_leases = []
            for lease in netxml_root.findall("ip/dhcp/host"):
                reserved_leases.append(lease.attrib["ip"])

            if self.vmspec.ip in reserved_leases:
                self.logger.error(
                    "%s is already reserved in %s", self.vmspec.ip, self.vmspec.net
                )

            # check if within the subnet
            net_ip = netxml_root.findall("ip")[0].attrib

            net_ip_addr = net_ip["address"]
            net_ip_mask = net_ip["netmask"]

            net_net = ipaddress.IPv4Network(
                f"{net_ip_addr}/{net_ip_mask}", strict=False
            )

            self.vmspec.gateway = self.vmspec.gateway or net_ip["address"]
            self.vmspec.bridge_pfxlen = net_net.prefixlen

            if ipaddress.ip_address(self.vmspec.ip) not in ipaddress.ip_network(
                net_net
            ):
                self.logger.error(
                    "% is not within %s: %s", self.vmspec.ip, self.vmspec.net, net_net
                )

            # check if within the dhcp range
            net_dhcp = netxml_root.findall("ip/dhcp/range")[0].attrib
            net_dhcp_start = int(
                ipaddress.ip_address(net_dhcp["start"]).packed.hex(), 16
            )
            net_dhcp_end = int(ipaddress.ip_address(net_dhcp["end"]).packed.hex(), 16)

            dhcp_range = []
            for ip in range(net_dhcp_start, net_dhcp_end):
                dhcp_range.append(ipaddress.ip_address(ip).exploded)

            if self.vmspec.ip not in dhcp_range:
                self.logger.error(
                    "%s is not within the DHCP range of %s. (%s - %s)",
                    self.vmspec.ip,
                    self.vmspec.net,
                    net_dhcp["start"],
                    net_dhcp["end"],
                )

            return needs_net_update

    def _gen_cloudinit_iso(self):
        self._cloudinit_iso = f"{self.vmspec.dom_name}-cloudinit.iso"

        clinit = CloudInit(self.vmspec)
        clinit.iso_path = f"{self._pool_path}/{self._cloudinit_iso}"
        clinit.mkiso()

        self._pool.refresh()

    def _gen_volume(self):
        self.logger.info("generating volumes")

        volxml_root = ET.Element("volume")
        ET.SubElement(volxml_root, "name").text = self.vmspec.vol_name
        ET.SubElement(volxml_root, "capacity", {"unit": "G"}).text = str(
            self.vmspec.vol_size
        )
        volxml_target = ET.SubElement(volxml_root, "target")
        ET.SubElement(volxml_target, "path").text = (
            f"{self._pool_path}/{self.vmspec.vol_name}"
        )
        ET.SubElement(volxml_target, "format", {"type": "qcow2"})

        volxml_backingstore = ET.SubElement(volxml_root, "backingStore")
        ET.SubElement(volxml_backingstore, "path").text = (
            f"{self._pool_path}/{self.vmspec.base_image}"
        )
        ET.SubElement(volxml_backingstore, "format", {"type": "qcow2"})
        volxml = ET.tostring(volxml_root, encoding="unicode")

        self._pool.createXML(volxml, 0)

    def _gen_dom(self):
        self.logger.info("generating the domain")

        domxml_root = ET.Element("domain", {"type": "kvm"})

        ET.SubElement(domxml_root, "name").text = self.vmspec.dom_name
        ET.SubElement(domxml_root, "memory", {"unit": "M"}).text = str(
            self.vmspec.dom_mem
        )
        ET.SubElement(domxml_root, "vcpu").text = str(self.vmspec.dom_vcpu)

        domxml_os = ET.SubElement(domxml_root, "os")
        ET.SubElement(domxml_os, "type", {"arch": "x86_64", "machine": "q35"}).text = (
            "hvm"
        )
        ET.SubElement(domxml_os, "boot", {"dev": "hd"})

        domxml_cpu = ET.SubElement(
            domxml_root, "cpu", {"mode": "custom", "match": "exact", "check": "partial"}
        )
        ET.SubElement(domxml_cpu, "model", {"fallback": "forbid"}).text = "qemu64"
        for feat in [
            "cx16",
            "popcnt",
            "sse4.1",
            "sse4.2",
            "ssse3",
            "avx",
            "hypervisor",
            "lahf_lm",
        ]:
            ET.SubElement(domxml_cpu, "feature", {"policy": "require", "name": feat})
        ET.SubElement(domxml_cpu, "feature", {"policy": "disable", "name": "svm"})

        domxml_dev = ET.SubElement(domxml_root, "devices")

        domxml_dev_disk = ET.SubElement(
            domxml_dev, "disk", {"type": "volume", "device": "disk"}
        )
        ET.SubElement(domxml_dev_disk, "driver", {"name": "qemu", "type": "qcow2"})
        ET.SubElement(
            domxml_dev_disk,
            "source",
            {"pool": self.vmspec.vol_pool, "volume": self.vmspec.vol_name},
        )
        ET.SubElement(domxml_dev_disk, "target", {"dev": "vda", "bus": "virtio"})
        ET.SubElement(domxml_dev_disk, "alias", {"name": "virtio-disk0"})

        domxml_dev_iso = ET.SubElement(
            domxml_dev, "disk", {"type": "volume", "device": "cdrom"}
        )
        ET.SubElement(domxml_dev_iso, "driver", {"name": "qemu", "type": "raw"})
        ET.SubElement(
            domxml_dev_iso,
            "source",
            {"pool": self.vmspec.vol_pool, "volume": self._cloudinit_iso},
        )
        ET.SubElement(domxml_dev_iso, "target", {"dev": "sda", "bus": "sata"})
        ET.SubElement(domxml_dev_iso, "readonly")

        domxml_dev_iface = ET.SubElement(domxml_dev, "interface", {"type": "network"})
        ET.SubElement(domxml_dev_iface, "source", {"network": self.vmspec.net})
        ET.SubElement(domxml_dev_iface, "mac", {"address": self.vmspec.mac_addr})
        ET.SubElement(domxml_dev_iface, "model", {"type": "virtio"})

        if self.vmspec.isolated_port is not None:
            isolated_opt = "no"
            if self.vmspec.isolated_port is True:
                isolated_opt = "yes"
            ET.SubElement(domxml_dev_iface, "port", {"isolated": isolated_opt})

        ET.SubElement(domxml_dev, "serial", {"type": "pty"})

        domxml = ET.tostring(domxml_root, encoding="unicode")

        self.logger.debug("DOM XML: %s", domxml)

        self.driver.defineXML(domxml)

    def _update_dhcp(self):
        self.logger.info("updating DHCP")

        netupdxml_root = ET.Element(
            "host",
            {
                "mac": self.vmspec.mac_addr,
                "name": self.vmspec.dom_name,
                "ip": self.vmspec.ip,
            },
        )
        netupdxml = ET.tostring(netupdxml_root, encoding="unicode")

        # virNetworkUpdate
        # (virNetworkPtr network,
        #       unsigned int command,
        #       unsigned int section,
        #       int parentIndex,
        #       const char * xml,
        #       unsigned int flags)
        #
        # parentIndex:
        # which parent element, if there are multiple parents of the same type
        # (e.g. which <ip> element when modifying a <dhcp>/<host> element), or
        # "-1" for "don't care" or "automatically find appropriate one".
        self._network.update(
            libvirt.VIR_NETWORK_UPDATE_COMMAND_ADD_FIRST,
            libvirt.VIR_NETWORK_SECTION_IP_DHCP_HOST,
            -1,
            netupdxml,
            libvirt.VIR_NETWORK_UPDATE_AFFECT_LIVE
            | libvirt.VIR_NETWORK_UPDATE_AFFECT_CONFIG,
        )

    def _update_dns(self):
        self.logger.info("updating DNS")

        dnsupdxml_root = ET.Element("host", {"ip": self.vmspec.ip})
        ET.SubElement(dnsupdxml_root, "hostname").text = self.vmspec.dom_name
        dnsupdxml = ET.tostring(dnsupdxml_root, encoding="unicode")

        self._network.update(
            libvirt.VIR_NETWORK_UPDATE_COMMAND_ADD_FIRST,
            libvirt.VIR_NETWORK_SECTION_DNS_HOST,
            -1,
            dnsupdxml,
            libvirt.VIR_NETWORK_UPDATE_AFFECT_LIVE
            | libvirt.VIR_NETWORK_UPDATE_AFFECT_CONFIG,
        )

    def _start_dom(self):
        self.logger.info("starting domain")

        domstart = self.driver.lookupByName(self.vmspec.dom_name)
        domstart.create()

    def create(self):
        self.logger.info("creating VM: %s", self.vmspec.dom_name)

        self._dom_exists_precheck()
        needs_net_update = self._network_precheck()

        # gen mac
        self.vmspec.mac_addr = self._genmac()

        # get _pool_path
        self._pool = self.driver.storagePoolLookupByName(self.vmspec.vol_pool)

        pool_xml = self._pool.XMLDesc()
        poolxml_tree = ET.ElementTree(ET.fromstring(pool_xml))
        poolxml_root = poolxml_tree.getroot()

        self._pool_path = poolxml_root.findall("target/path")[0].text
        self._gen_cloudinit_iso()
        self._gen_volume()
        self._gen_dom()

        if needs_net_update:
            self._update_dhcp()
            self._update_dns()

        self._start_dom()


class APIDriver:
    def __init__(self, url="qemu:///system"):
        self.url = url

        self.logger = logging.getLogger(self.__class__.__name__)

        self.conn = None
        self._libvirt_gid = None

    def __getattribute__(self, name):
        try:
            attr = object.__getattribute__(self, name)

            return attr
        except AttributeError:
            pass

        attr = self.conn.__getattribute__(name)
        if hasattr(attr, "__call__"):

            @wraps(attr)
            def newfunc(*args, **kwargs):
                self.logger.debug("before calling %s", attr.__name__)
                result = attr(*args, **kwargs)
                self.logger.debug("done calling %s", attr.__name__)

                return result

            return newfunc

        return attr

    def _check_perms(self):
        uid = os.getuid()
        user = pwd.getpwuid(uid)
        usergroups = os.getgrouplist(user.pw_name, user.pw_gid)

        try:
            libvirt_gid = grp.getgrnam("libvirtd").gr_gid
        except KeyError:
            try:
                libvirt_gid = grp.getgrnam("libvirt").gr_gid
            except KeyError:
                self.logger.exception("libVirt access group does not exist")

        if libvirt_gid not in usergroups:
            err_msg = f"{user.pw_name} is not a member of the libVirt access"
            err_msg += "group. cannot call qemu:///system."

            self.logger.error("%s", err_msg)

        self._libvirt_gid = libvirt_gid

    def nuke(self, dom_name):
        nuker = APIDriverVMNuker(self, dom_name)
        nuker.nuke()

    def create(self, vmspec):
        self.logger.debug("Creating with VMspec %s", vmspec.__dict__)
        creator = APIDriverVMCreator(self, vmspec)
        creator.create()

    @staticmethod
    def _libvirt_callback(userdata, err):
        pass

    def connect(self):
        self._check_perms()

        # libvirt exceptions, even when they are caught, print out the error
        # message for some reason, hijack the handler instead
        libvirt.registerErrorHandler(f=self._libvirt_callback, ctx=None)

        self.logger.info("connecting to the libVirt API")

        self.conn = libvirt.open("qemu:///system")
