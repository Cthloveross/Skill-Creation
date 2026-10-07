"""Linux ioctl number encoding helpers.

Encoding (little bits -> high bits):
  nr   : bits 0-7
  type : bits 8-15
  size : bits 16-29
  dir  : bits 30-31  (none=0, write=1, read=2, readwrite=3)
"""

DIR_NONE = 0
DIR_WRITE = 1   # _IOW  -> 0x40000000
DIR_READ = 2    # _IOR  -> 0x80000000
DIR_RW = 3      # _IOWR -> 0xC0000000

_NRSHIFT = 0
_TYPESHIFT = 8
_SIZESHIFT = 16
_DIRSHIFT = 30


def ioc(direction, typ, nr, size):
    """Return the 32-bit ioctl command number as an unsigned int."""
    return ((direction << _DIRSHIFT)
            | (size << _SIZESHIFT)
            | (typ << _TYPESHIFT)
            | (nr << _NRSHIFT)) & 0xFFFFFFFF


def io(typ, nr):
    return ioc(DIR_NONE, typ, nr, 0)


def ior(typ, nr, size):
    return ioc(DIR_READ, typ, nr, size)


def iow(typ, nr, size):
    return ioc(DIR_WRITE, typ, nr, size)
