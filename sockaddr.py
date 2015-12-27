import socket
import ctypes

# the following sockaddr related code is taken from
# https://www.osso.nl/blog/python-ctypes-socket-datagram/

def SUN_LEN(path):
    """For AF_UNIX the addrlen is *not* sizeof(struct sockaddr_un)"""
    return ctypes.c_int(2 + len(path))

UNIX_PATH_MAX = 108
PF_UNIX = socket.AF_UNIX
PF_INET = socket.AF_INET

class sockaddr_un(ctypes.Structure):
    _fields_ = [("sa_family", ctypes.c_ushort),  # sun_family
                ("sun_path", ctypes.c_char * UNIX_PATH_MAX)]

class sockaddr_in(ctypes.Structure):
    _fields_ = [("sa_family", ctypes.c_ushort),  # sin_family
                ("sin_port", ctypes.c_ushort),
                ("sin_addr", ctypes.c_byte * 4),
                ("__pad", ctypes.c_byte * 8)]    # struct sockaddr_in is 16 bytes

# For compatibility with Python-socket, AF_UNIX uses a string address
# and AF_INET uses an (ip_address, port) tuple.
def to_sockaddr(family, address=None):
    if family == socket.AF_UNIX:
        addr = sockaddr_un()
        addr.sa_family = ctypes.c_ushort(family)
        if address:
            addr.sun_path = address
            addrlen = SUN_LEN(address)
        else:
            addrlen = ctypes.c_int(ctypes.sizeof(addr))
    elif family == socket.AF_INET:
        addr = sockaddr_in()
        addr.sa_family = ctypes.c_ushort(family)
        if address:
            addr.sin_port = ctypes.c_ushort(socket.htons(address[1]))
            bytes_ = [int(i) for i in address[0].split('.')]
            addr.sin_addr = (ctypes.c_byte * 4)(*bytes_)
        addrlen = ctypes.c_int(ctypes.sizeof(addr))
    else:
        raise NotImplementedError('Not implemented family %s' % (family,))

    return addr, addrlen

def from_sockaddr(sockaddr):
    if sockaddr.sa_family == socket.AF_UNIX:
        return sockaddr.sun_path
    elif sockaddr.sa_family == socket.AF_INET:
        return ('%d.%d.%d.%d' % tuple(sockaddr.sin_addr),
                socket.ntohs(sockaddr.sin_port))
    raise NotImplementedError('Not implemented family %s' %
                              (sockaddr.sa_family,))
