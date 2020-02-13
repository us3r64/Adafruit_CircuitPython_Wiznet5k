# The MIT License (MIT)
#
# Copyright (c) 2020 Brent Rubell for Adafruit Industries
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
"""
`adafruit_wiznet5k`
================================================================================

Pure-Python interface for WIZNET 5k ethernet modules.


* Author(s): Brent Rubell

Implementation Notes
--------------------

**Hardware:**


**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://github.com/adafruit/circuitpython/releases


# * Adafruit's Bus Device library: https://github.com/adafruit/Adafruit_CircuitPython_BusDevice
"""

# imports
import time
import adafruit_bus_device.spi_device as spidev
from micropython import const
from digitalio import DigitalInOut
from adafruit_wiznet5k.adafruit_wiznet5k_dhcp import DHCP as DHCP

__version__ = "0.0.0-auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_Wiznet5k.git"

# Wiznet5k Registers
REG_MR             = const(0x0000) # Mode
REG_GAR            = const(0x0001) # Gateway IP Address
REG_SUBR           = const(0x0005) # Subnet Mask Address
REG_VERSIONR_W5500 = const(0x0039) # W5500 Silicon Version
REG_SHAR           = const(0x0009) # Source Hardware Address
REG_SIPR           = const(0x000F) # Source IP Address
REG_PHYCFGR        = const(0x002E) # W5500 PHY Configuration

# Wiznet5k Socket Registers
REG_SNMR           = const(0x0000) # Socket n Mode
REG_SNCR           = const(0x0001) # Socket n Command
REG_SNIR           = const(0x0002) # Socket n Interrupt
REG_SNSR           = const(0x0003) # Socket n Status
REG_SNPORT         = const(0x0004) # Socket n Source Port
REG_SNDIPR         = const(0x000C) # Destination IP Address
REG_SNDPORT        = const(0x0010) # Destination Port
REG_SNRX_RSR       = const(0x0026) # RX Free Size
REG_SNRX_RD        = const(0x0028) # Read Size Pointer
REG_SNTX_FSR       = const(0x0020) # Socket n TX Free Size
REG_SNTX_WR        = const(0x0024) # TX Write Pointer


# SNSR Commands
SNSR_SOCK_CLOSED      = const(0x00)
SNSR_SOCK_INIT        = const(0x13)
SNSR_SOCK_LISTEN      = const(0x14)
SNSR_SOCK_SYNSENT     = const(0x15)
SNSR_SOCK_SYNRECV     = const(0x16)
SNSR_SOCK_ESTABLISHED = const(0x17)
SNSR_SOCK_FIN_WAIT    = const(0x18)
SNSR_SOCK_CLOSING     = const(0x1A)
SNSR_SOCK_TIME_WAIT   = const(0x1B)
SNSR_SOCK_CLOSE_WAIT  = const(0x1C)
SNSR_SOCK_LAST_ACK    = const(0x1D)
SNSR_SOCK_UDP         = const(0x22)
SNSR_SOCK_IPRAW       = const(0x32)
SNSR_SOCK_MACRAW      = const(0x42)
SNSR_SOCK_PPPOE       = const(0x5F)

# Sock Commands (CMD)
CMD_SOCK_OPEN      = const(0x01)
CMD_SOCK_LISTEN    = const(0x02)
CMD_SOCK_CONNECT   = const(0x04)
CMD_SOCK_DISCON    = const(0x08)
CMD_SOCK_CLOSE     = const(0x10)
CMD_SOCK_SEND      = const(0x20)
CMD_SOCK_SEND_MAC  = const(0x21)
CMD_SOCK_SEND_KEEP = const(0x22)
CMD_SOCK_RECV      = const(0x40)


# Socket n Interrupt Register
SNIR_SEND_OK = const(0x10)
SNIR_TIMEOUT = const(0x08)
SNIR_RECV    = const(0x04)
SNIR_DISCON  = const(0x02)
SNIR_CON     = const(0x01)

CH_SIZE     = const(0x100)
SOCK_SIZE   = const(0x800) # MAX W5k socket size
# Register commands
MR_RST = const(0x80) # Mode Register RST


# Default hardware MAC address
DEFAULT_MAC = [0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0xED]
# Maximum number of sockets to support, differs between chip versions.
W5200_W5500_MAX_SOCK_NUM = const(0x08)


class WIZNET:
    """Interface for WIZNET5k module.
    :param ~busio.SPI spi_bus: The SPI bus the Wiznet module is connected to.
    :param ~digitalio.DigitalInOut cs: Chip select pin.
    :param ~digitalio.DigitalInOut rst: Optional reset pin. 
    :param bool dhcp: Whether to start DHCP automatically or not.
    :param str mac: The Wiznet's MAC Address.
    :param bool debug: Enable debugging output.

    """

    # Socket registers
    SNMR_CLOSE  = const(0x00)
    SNMR_TCP    = const(0x21)
    SNMR_UDP    = const(0x02)
    SNMR_IPRAW  = const(0x03)
    SNMR_MACRAW = const(0x04)
    SNMR_PPPOE  = const(0x05)

    def __init__(self, spi_bus, cs, reset=None, 
                 dhcp=True, mac=DEFAULT_MAC, debug=True):
        self._debug = debug
        self._device = spidev.SPIDevice(spi_bus, cs,
                                        baudrate=8000000,
                                        polarity=0, phase=0)
        self._chip_type = None
        # init c.s.
        self._cs = cs
        # initialize the module
        assert self._w5100_init() == 1, "Unsuccessfully initialized Wiznet module."
        # Set MAC address
        self.mac_address = mac
        # Set DHCP
        self.is_dhcp = dhcp
        self._sock = 0
        self._src_port = 0

    @property
    def dhcp(self):
        """Returns if DHCP is active.
        """
        return self.is_dhcp
    
    @dhcp.setter
    def dhcp(self, dhcp):
        self.is_dhcp = dhcp

    @property
    def max_sockets(self):
        """Returns max number of sockets supported by chip.
        """
        if self._chip_type == "w5500":
            return W5200_W5500_MAX_SOCK_NUM
        else:
            return -1

    @property
    def chip(self):
        """Returns the chip type.
        """
        if self._debug:
            print("Chip version")
        return self._chip_type

    @property
    def ip_address(self):
        """Returns the hardware's IP address.
        """
        return self.read(REG_SIPR, 0x00, 4)

    @ip_address.setter
    def ip_address(self, ip_address):
        """Returns the hardware's IP address.
        :param tuple ip_address: Desired IP address.
        """
        self._write_n(REG_SIPR, 0x04, ip_address)

    @property
    def mac_address(self):
        """Returns the hardware's MAC address.

        """
        return self.read(REG_SHAR, 0x00, 6)

    @mac_address.setter
    def mac_address(self, address):
        """Sets the hardware MAC address.
        :param tuple address: Hardware MAC address.

        """
        self._write_n(REG_SHAR, 0x04, address)

    @property
    def link_status(self):
        """"Returns if the PHY is connected.
        """
        if self._chip_type == "w5500":
            data =  self.read(REG_PHYCFGR, 0x00)
            return data[0] & 0x01
        else:
            return 0

    @property
    def remote_ip(self):
        """Returns the remote IP Address.
        """
        remote_ip = bytearray(4)
        if self._sock >= self.max_sockets:
            return remote_ip
        for octet in range(0, 4):
             remote_ip[octet] = self._read_socket(self._sock, REG_SNDIPR+octet)[0]
        return self.pretty_ip(remote_ip)


    def pretty_ip(self, ip): # pylint: disable=no-self-use, invalid-name
        """Converts a bytearray IP address to a
        dotted-quad string for printing

        """
        return "%d.%d.%d.%d" % (ip[0], ip[1], ip[2], ip[3])

    def pretty_mac(self, mac): # pylint: disable=no-self-use, invalid-name
        """Converts a bytearray MAC address to a
        dotted-quad string for printing

        """
        return "%s:%s:%s:%s:%s:%s" % (hex(mac[0]), hex(mac[1]), hex(mac[2]),
                                      hex(mac[3]), hex(mac[4]), hex(mac[5]))

    @property
    def ifconfig(self):
        """Returns a tuple of (ip_address, subnet_mask, gateway_address, dns_server).
        """
        for octet in range(0, 4):
            subnet_mask = self.read(REG_SUBR+octet, 0x00)
        params = (self.ip_address, subnet_mask, 0, self._dns)

    @ip_address.setter
    def ifconfig(self, params):
        """Sets ifconfig parameters provided tuple of
        (ip_address, subnet_mask, gateway_address, dns_server).
        Setting if_config turns DHCP off, if on.
        """
        ip_address, subnet_mask, gateway_address, dns_server = params
        # set ip_address
        self.ip_address = ip_address
        # set subnet_address
        for octet in range(0, 4):
            self.write(REG_SUBR+octet, 0x04, subnet_mask[octet])
        # set gateway_address
        for octet in range(0, 4):
            self.write(REG_GAR+octet, 0x04, gateway_address[octet])
        # set dns
        self._dns = dns_server
        self.dhcp = False

    def _w5100_init(self):
        """Initializes and detects a wiznet5k module.

        """
        time.sleep(1)
        self._cs.switch_to_output()
        self._cs.value = 1

        # Detect if chip is Wiznet W5500
        if self.detect_w5500() == 1:
            # perform w5500 initialization
            for i in range(0, W5200_W5500_MAX_SOCK_NUM):
                ctrl_byte = (0x0C + (i<<5))
                self.write(0x1E, ctrl_byte, 2)
                self.write(0x1F, ctrl_byte, 2)
        else:
            return 0
        return 1

    def detect_w5500(self):
        """Detects W5500 chip.

        """
        assert self.sw_reset() == 0, "Chip not reset properly!"
        self._write_mr(0x08)
        assert self._read_mr()[0] == 0x08, "Expected 0x08."

        self._write_mr(0x10)
        assert self._read_mr()[0] == 0x10, "Expected 0x10."

        self._write_mr(0x00)
        assert self._read_mr()[0] == 0x00, "Expected 0x00."

        if self.read(REG_VERSIONR_W5500, 0x00)[0] != 0x04:
            return -1
        self._chip_type = "w5500"
        self._ch_base_msb = 0x10
        return 1

    def sw_reset(self):
        """Performs a soft-reset on a Wiznet chip
        by writing to its MR register reset bit.

        """
        mr = self._read_mr()
        self._write_mr(0x80)
        mr = self._read_mr()
        if mr[0] != 0x00:
            return -1
        return 0

    def _read_mr(self):
        """Reads from the Mode Register (MR).

        """
        res = self.read(REG_MR, 0x00)
        return res

    def _write_mr(self, data):
        """Writes to the mode register (MR).
        :param int data: Data to write to the mode register.

        """
        self.write(REG_MR, 0x04, data)

    def read(self, addr, cb, length=1, buffer=None):
        """Reads data from a register address.
        :param int addr: Register address.
        :param int cb: Common register block (?)

        """
        with self._device as bus_device:
            bus_device.write(bytes([addr >> 8]))
            bus_device.write(bytes([addr & 0xFF]))
            bus_device.write(bytes([cb]))
            if buffer is None:
                result = bytearray(length)
                bus_device.readinto(result)
                return result
            bus_device.readinto(buffer, end=length)

    def write(self, addr, cb, data):
        """Writes data to a register address.
        :param int addr: Register address.
        :param int cb: Common register block (?)
        :param int data: Data to write to the register.

        """
        with self._device as bus_device:
            bus_device.write(bytes([addr >> 8]))
            bus_device.write(bytes([addr & 0xFF]))
            bus_device.write(bytes([cb]))
            bus_device.write(bytes([data]))

    def _write_n(self, addr, cb, data):
        """Writes data to a register address.
        :param int addr: Register address.
        :param int data: Data to write to the register.
        :param int len: Length of data to write.

        """
        with self._device as bus_device:
            bus_device.write(bytes([addr >> 8]))
            bus_device.write(bytes([addr & 0xFF]))
            bus_device.write(bytes([cb]))
            for i in range(0, len(data)):
                bus_device.write(bytes([data[i]]))
        return len

    # Socket-Register API

    def socket_available(self, socket_num):
        """Returns bytes to be read from socket.
        """
        assert socket_num <= self.max_sockets, "Provided socket exceeds max_sockets."
        res = self._get_rx_rcv_size(socket_num)
        return int.from_bytes(res, 'b')

    def socket_status(self, socket_num):
        """Returns the socket connection status. Can be: SNSR_SOCK_CLOSED,
        SNSR_SOCK_INIT, SNSR_SOCK_LISTEN, SNSR_SOCK_SYNSENT, SNSR_SOCK_SYNRECV,
        SNSR_SYN_SOCK_ESTABLISHED, SNSR_SOCK_FIN_WAIT, SNSR_SOCK_CLOSING,
        SNSR_SOCK_TIME_WAIT, SNSR_SOCK_CLOSE_WAIT, SNSR_LAST_ACK,
        SNSR_SOCK_UDP, SNSR_SOCK_IPRAW, SNSR_SOCK_MACRAW, SNSR_SOCK_PPOE.
        """
        return self._read_snsr(socket_num)

    def socket_connect(self, socket_num, dest, port, conn_mode=SNMR_TCP):
        """Open and verify we've connected a socket to a dest IP address
        or hostname. By default, we use 'conn_mode'= SNMR_TCP but we
        may also use SNMR_UDP.
        """
        assert self.link_status, "Ethernet cable disconnected!"
        if self._debug:
            print("*** Connecting: Socket# {}, conn_mode: {}".format(socket_num,conn_mode))
        # initialize a socket and set the mode
        res = self.socket_open(socket_num, dest, port, conn_mode = conn_mode)
        if res == 1: # socket unsuccessfully opened
            raise RuntimeError('Failed to initalize a connection with the socket.')

        if conn_mode == SNMR_TCP:
            # TCP client - connect socket
            self._write_sncr(self._sock, CMD_SOCK_CONNECT)
            self._read_sncr(self._sock)
            # wait for tcp connection establishment
            while self.socket_status(socket_num)[0] != SNSR_SOCK_ESTABLISHED:
                if self.socket_status(socket_num)[0] == SNSR_SOCK_CLOSED:
                    raise RuntimeError('Failed to establish connection.')
                time.sleep(1)
        return 1

    def get_socket(self):
        """Request, allocates and returns a socket from the W5k
        chip. Returned socket number may not exceed max_sockets. 
        """
        if self._debug:
            print("*** Get socket")
        sock = 0
        for _sock in range(0, self.max_sockets):
            status = self.socket_status(_sock)
            if status[0] == SNSR_SOCK_CLOSED or status[0] == SNSR_SOCK_FIN_WAIT or status[0] == SNSR_SOCK_CLOSE_WAIT:
                sock = _sock
                break

        if sock == self.max_sockets:
            return 0
        self._src_port+=1

        if (self._src_port == 0):
            self._src_port = 1024
        if self._debug:
            print("Allocated socket #%d" % sock)
        return sock

    def socket_open(self, socket_num, dest, port, conn_mode=SNMR_TCP):
        """Opens a socket to a destination IP address or hostname. By default, we use
        'conn_mode'=SNMR_TCP but we may also use SNMR_UDP.
        """
        assert self.link_status, "Ethernet cable disconnected!"
        if self._debug:
            print("*** Open socket")
        if self._read_snsr(socket_num)[0] == SNSR_SOCK_CLOSED:
            print("w5k socket begin, protocol={}, port={}".format(conn_mode, port))
            time.sleep(0.00025)

            self._write_snmr(socket_num, conn_mode)
            self._write_snir(socket_num, 0xFF)

            if self._src_port > 0:
                # write to socket source port
                self._write_sock_port(socket_num, self._src_port)
            else:
                # if source port is not set, set the local port number
                self._write_sock_port(socket_num, LOCAL_PORT)

            # set socket destination IP and port
            self._write_sndipr(socket_num, dest)
            self._write_sndport(socket_num, port)

            # open socket
            self._write_sncr(socket_num, CMD_SOCK_OPEN)
            self._read_sncr(socket_num)
            assert self._read_snsr((socket_num))[0] == 0x13 or self._read_snsr((socket_num))[0] == 0x22, \
                "Could not open socket in TCP or UDP mode."
            return 0
        return 1

    def socket_close(self, socket_num):
        """Closes a socket.

        """
        assert self.link_status, "Ethernet cable disconnected!"
        if self._debug:
            print("*** Closing socket #%d" % socket_num)
        self._write_sncr(socket_num, CMD_SOCK_CLOSE)
        self._read_sncr(socket_num)
        self._write_snir(socket_num, 0xFF)

    def socket_read(self, socket_num, length):
        """Reads data from a socket into a buffer.
        Returns buffer.

        """
        assert self.link_status, "Ethernet cable disconnected!"
        assert socket_num <= self.max_sockets, "Provided socket exceeds max_sockets."
        # Check if there is data available on the socket
        ret = self._get_rx_rcv_size(socket_num)
        ret = int.from_bytes(ret, 'b')
        if self._debug:
            print("Bytes avail. on sock: ", ret)
        if ret == 0:
            # no data on socket?
            status = self.socket_status(socket_num)
            if(status == SNSR_SOCK_LISTEN or status == SNSR_SOCK_CLOSED or status == SNSR_SOCK_CLOSE_WAIT):
                # remote end closed its side of the connection, EOF state
                ret = 0
            else:
                # connection is alive, no data waiting to be read
                ret = -1
        elif ret > length:
            # set ret to the length of buffer
            ret = length

        if ret > 0:
            if self._debug:
                print('\t * Processing {} bytes of data'.format(ret))
            # Read the starting save address of the received data
            ptr = self._read_snrx_rd(socket_num)

            # Read data from the starting address of snrx_rd
            ctrl_byte = (0x18+(socket_num<<5))

            print("Read data, len={}, at: {}".format(ret, ptr))
            resp = self.read(ptr, ctrl_byte, ret)

            #  After reading the received data, update Sn_RX_RD to the increased
            # value as many as the reading size.
            ptr += ret
            self._write_snrx_rd(socket_num, ptr)

            # Notify the W5k of the updated Sn_Rx_RD
            self._write_sncr(socket_num, CMD_SOCK_RECV)
            self._read_sncr(socket_num)
        return ret, resp

    def socket_write(self, socket_num, buffer):
        """Writes a bytearray to a provided socket.

        """
        assert self.link_status, "Ethernet cable disconnected!"
        assert socket_num <= self.max_sockets, "Provided socket exceeds max_sockets."
        status = 0
        ret = 0
        free_size = 0
        if len(buffer) > SOCK_SIZE:
            ret = SOCK_SIZE
        else:
            ret = len(buffer)

        # if buffer is available, start the transfer
        free_size = self._get_tx_free_size(socket_num)
        while (free_size < ret):
            free_size = self._get_tx_free_size(socket_num)
            status = self.socket_status(socket_num)
            if (status != SNSR_SOCK_ESTABLISHED) and (status != SNSR_SOCK_CLOSE_WAIT):
                ret = 0
                break

        # Read the starting address for saving the transmitting data.
        ptr = self._read_sntx_wr(socket_num)
        offset = ptr & 0x07FF
        dst_addr = offset +  (socket_num * 2048 + 0x8000)

        # update sn_tx_wr to the value + data size
        ptr += len(buffer)
        self._write_sntx_wr(socket_num, ptr)

        cntl_byte = (0x14+(socket_num<<5))
        self._write_n(dst_addr, cntl_byte, buffer)

        self._write_sncr(socket_num, CMD_SOCK_SEND)
        self._read_sncr(socket_num)

        # check data was  transferred correctly
        while(self._read_snir(socket_num)[0] & SNIR_SEND_OK) != SNIR_SEND_OK:
            if self.socket_status(socket_num) == SNSR_SOCK_CLOSED:
                self.socket_close(socket_num)
                return 0
            time.sleep(0.01)

        self._write_snir(socket_num, SNIR_SEND_OK)
        return ret

    # Socket-Register Methods

    def _get_rx_rcv_size(self, sock):
        """Get size of recieved and saved in socket buffer.

        """
        val = 0
        val_1 = self._read_snrx_rsr(sock)
        while (val != val_1):
            val = self._read_snrx_rsr(sock)
        return val

    def _get_tx_free_size(self, sock):
        """Get free size of sock's tx buffer block.

        """
        val = 0
        val_1 = 0
        while (val != val_1):
            val_1 = self._read_sntx_fsr(sock)
            if val_1 != 0:
                val = self._read_sntx_fsr(sock)
        return val

    def _read_snrx_rd(self, sock):
        buf = bytearray(2)
        buf[0] = self._read_socket(sock, REG_SNRX_RD)[0]
        buf[1] = self._read_socket(sock, REG_SNRX_RD+1)[0]
        return (buf[0] << 8 | buf[1])


    def _write_snrx_rd(self, sock, data):
        self._write_socket(sock, REG_SNRX_RD, data >> 8)
        self._write_socket(sock, REG_SNRX_RD+1, data & 0xff)

    def _write_sntx_wr(self, sock, data):
        self._write_socket(sock, REG_SNTX_WR, data >> 8)
        self._write_socket(sock, REG_SNTX_WR+1, data & 0xff)

    def _read_sntx_wr(self, sock):
        buf = bytearray(2)
        buf[0] = self._read_socket(sock, 0x0024)[0]
        buf[1] = self._read_socket(sock, 0x0024+1)[0]
        return (buf[0] << 8 | buf[1])


    def _read_sntx_fsr(self, sock):
        data = self._read_socket(sock, REG_SNTX_FSR)
        data += self._read_socket(sock, REG_SNTX_FSR+1)
        return data

    def _read_snrx_rsr(self, sock):
        data = self._read_socket(sock, REG_SNRX_RSR)
        data += self._read_socket(sock, REG_SNRX_RSR+1)
        return data

    def _write_sndipr(self, sock, ip_addr):
        """Writes to socket destination IP Address.

        """
        for octet in range(0, 4):
            self._write_socket(sock, REG_SNDIPR+octet, ip_addr[octet])

    def _write_sndport(self, sock, port):
        """Writes to socket destination port.

        """
        self._write_socket(sock, REG_SNDPORT, port >> 8)
        self._write_socket(sock, REG_SNDPORT+1, port & 0xFF)

    def _read_snsr(self, sock):
        """Reads Socket n Status Register.

        """
        return self._read_socket(sock, REG_SNSR)

    def _read_snmr(self, sock, protocol):
        """Read Socket n Mode Register

        """
        return self._read_socket(sock, protocol)

    def _write_snmr(self, sock, protocol):
        """Write to Socket n Mode Register.

        """
        self._write_socket(sock, REG_SNMR, protocol)

    def _write_snir(self, sock, data):
        """Write to Socket n Interrupt Register.
        """
        self._write_socket(sock, REG_SNIR, data)

    def _write_sock_port(self, sock, port):
        """Write to the socket port number.
        """
        self._write_socket(sock, REG_SNPORT, port >> 8)
        self._write_socket(sock, REG_SNPORT+1, port & 0xFF)

    def _write_sncr(self, sock, data):
        self._write_socket(sock, REG_SNCR, data)

    def _read_sncr(self, sock):
        return self._read_socket(sock, REG_SNCR)

    def _read_snmr(self, sock):
        return self._read_socket(sock, REG_SNMR)

    def _read_snir(self, sock):
        return self._read_socket(sock, REG_SNIR)
    
    def _read_sndipr(self, sock):
        return self._read_socket(sock, REG_SNDIPR)

    def _write_socket(self, sock, address, data, length=None):
        """Write to a W5k socket register.
        """
        base = self._ch_base_msb << 8
        cntl_byte = (sock<<5)+0x0C;
        if length is None:
            return self.write(base + sock * CH_SIZE + address, cntl_byte, data)
        return self._write_n(base + sock * CH_SIZE + address, cntl_byte, data)

    def _read_socket(self, sock, address):
        """Read a W5k socket register.
        """
        cntl_byte = (sock<<5)+0x08;
        return self.read(address, cntl_byte)
