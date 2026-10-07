# ppdev ioctl reference (from <linux/ppdev.h>, type char 'p' = 0x70)

Encoding: value = dir<<30 | size<<16 | 0x70<<8 | nr
(dir: _IO=0, _IOW=1=0x40000000, _IOR=2=0x80000000)

Pointer direction in syzlang (user-space view):
_IOR -> ptr[out, ...], _IOW -> ptr[in, ...], _IO -> no third arg.

| Name        | Macro | nr   | C type               | size | syzlang arg |
|-------------|-------|------|----------------------|------|-------------|
| PPSETMODE   | _IOW  | 0x80 | int                  | 4    | ptr[in, flags[ieee1284_modes, int32]] |
| PPRSTATUS   | _IOR  | 0x81 | unsigned char        | 1    | ptr[out, int8] |
| PPRCONTROL  | _IOR  | 0x83 | unsigned char        | 1    | ptr[out, int8] |
| PPWCONTROL  | _IOW  | 0x84 | unsigned char        | 1    | ptr[in, int8] |
| PPFCONTROL  | _IOW  | 0x85 | ppdev_frob_struct    | 2    | ptr[in, ppdev_frob_struct] |
| PPRDATA     | _IOR  | 0x86 | unsigned char        | 1    | ptr[out, int8] |
| PPWDATA     | _IOW  | 0x87 | unsigned char        | 1    | ptr[in, int8] |
| PPCLAIM     | _IO   | 0x8b | (none)               | 0    | (none) |
| PPRELEASE   | _IO   | 0x8c | (none)               | 0    | (none) |
| PPYIELD     | _IO   | 0x8d | (none)               | 0    | (none) |
| PPEXCL      | _IO   | 0x8f | (none)               | 0    | (none) |
| PPDATADIR   | _IOW  | 0x90 | int                  | 4    | ptr[in, int32] |
| PPNEGOT     | _IOW  | 0x91 | int                  | 4    | ptr[in, flags[ieee1284_modes, int32]] |
| PPWCTLONIRQ | _IOW  | 0x92 | unsigned char        | 1    | ptr[in, int8] |
| PPCLRIRQ    | _IOR  | 0x93 | int                  | 4    | ptr[out, int32] |
| PPSETPHASE  | _IOW  | 0x94 | int                  | 4    | ptr[in, int32] |
| PPGETTIME   | _IOR  | 0x95 | struct timeval       | 16/8 | ptr[out, timeval] |
| PPSETTIME   | _IOW  | 0x96 | struct timeval       | 16/8 | ptr[in, timeval] |
| PPGETMODES  | _IOR  | 0x97 | unsigned int         | 4    | ptr[out, int32] |
| PPGETMODE   | _IOR  | 0x98 | int                  | 4    | ptr[out, int32] |
| PPGETPHASE  | _IOR  | 0x99 | int                  | 4    | ptr[out, int32] |
| PPGETFLAGS  | _IOR  | 0x9a | int                  | 4    | ptr[out, flags[ppdev_flags, int32]] |
| PPSETFLAGS  | _IOW  | 0x9b | int                  | 4    | ptr[in, flags[ppdev_flags, int32]] |

23 ioctls total. struct timeval is 16 bytes on amd64, 8 on 386, so PPGETTIME
and PPSETTIME get per-arch const values.

## IEEE1284 mode flags (<linux/parport.h>)

| Name | Value |
|------|-------|
| IEEE1284_MODE_NIBBLE | 0 |
| IEEE1284_MODE_BYTE   | 1 |
| IEEE1284_MODE_COMPAT | 256 |
| IEEE1284_MODE_BECP   | 512 |
| IEEE1284_MODE_ECP    | 16 |
| IEEE1284_MODE_ECPRLE | 48 |
| IEEE1284_MODE_ECPSWE | 64 |
| IEEE1284_MODE_EPP    | 8 |
| IEEE1284_MODE_EPPSWE | 128 |
| IEEE1284_DEVICEID    | 4 |
| IEEE1284_EXT_LINK    | 16384 |

## ppdev flags (<linux/ppdev.h>)

| Name | Value |
|------|-------|
| PP_FASTWRITE | 4 |
| PP_FASTREAD  | 8 |
| PP_W91284PIC | 16 |

Worked check: PPSETMODE = _IOW('p',0x80,int) =
0x40000000 | (4<<16) | (0x70<<8) | 0x80 = 0x40047080 = 1074032768.
