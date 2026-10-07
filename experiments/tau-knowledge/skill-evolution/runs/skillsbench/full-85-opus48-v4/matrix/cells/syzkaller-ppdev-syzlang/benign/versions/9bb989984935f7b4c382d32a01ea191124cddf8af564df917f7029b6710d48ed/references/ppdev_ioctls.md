# ppdev ioctl reference (from <linux/ppdev.h>, type char 'p' = 0x70)

Encoding: value = dir<<30 | size<<16 | 0x70<<8 | nr
(dir: _IO=0, _IOW=1=0x40000000, _IOR=2=0x80000000)

Pointer direction in syzlang (user-space view):
_IOR -> ptr[out, ...], _IOW -> ptr[in, ...], _IO -> no third arg.

IMPORTANT: the `nr` numbers below are taken verbatim from <linux/ppdev.h>.
Note the easy-to-miss ordering: PPRDATA=0x85, PPWDATA=0x86 and
PPFCONTROL=0x8e (PPFCONTROL is NOT 0x85). Do not guess sequential nr values.

| Name        | Macro | nr   | C type               | size | syzlang arg |
|-------------|-------|------|----------------------|------|-------------|
| PPSETMODE   | _IOW  | 0x80 | int                  | 4    | ptr[in, flags[ieee1284_modes, int32]] |
| PPRSTATUS   | _IOR  | 0x81 | unsigned char        | 1    | ptr[out, int8] |
| PPRCONTROL  | _IOR  | 0x83 | unsigned char        | 1    | ptr[out, int8] |
| PPWCONTROL  | _IOW  | 0x84 | unsigned char        | 1    | ptr[in, int8] |
| PPRDATA     | _IOR  | 0x85 | unsigned char        | 1    | ptr[out, int8] |
| PPWDATA     | _IOW  | 0x86 | unsigned char        | 1    | ptr[in, int8] |
| PPFCONTROL  | _IOW  | 0x8e | ppdev_frob_struct    | 2    | ptr[in, ppdev_frob_struct] |
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
and PPSETTIME get per-arch const values (see const-file syntax below).

Expected amd64 ioctl numbers (decimal) as a cross-check:
PPSETMODE=1074032768, PPRSTATUS=2147577985, PPRCONTROL=2147577987,
PPWCONTROL=1073836164, PPRDATA=2147577989, PPWDATA=1073836166,
PPFCONTROL=1073901710, PPCLAIM=28811, PPRELEASE=28812, PPYIELD=28813,
PPEXCL=28815, PPDATADIR=1074032784, PPNEGOT=1074032785,
PPWCTLONIRQ=1073836178, PPCLRIRQ=2147774611, PPSETPHASE=1074032788,
PPGETTIME(amd64)=2148561045, PPSETTIME(amd64)=1074819222,
PPGETMODES=2147774615, PPGETMODE=2147774616, PPGETPHASE=2147774617,
PPGETFLAGS=2147774618, PPSETFLAGS=1074032795.

## IEEE1284 mode flags (<linux/parport.h>, bit positions matter!)

| Name | Expression | Value |
|------|-----------|-------|
| IEEE1284_MODE_NIBBLE | 0        | 0 |
| IEEE1284_MODE_BYTE   | 1<<0     | 1 |
| IEEE1284_MODE_COMPAT | 1<<8     | 256 |
| IEEE1284_MODE_BECP   | 1<<9     | 512 |
| IEEE1284_MODE_ECP    | 1<<4     | 16 |
| IEEE1284_MODE_ECPRLE | ECP|1<<5 | 48 |
| IEEE1284_MODE_ECPSWE | 1<<10    | 1024 |
| IEEE1284_MODE_EPP    | 1<<6     | 64 |
| IEEE1284_MODE_EPPSL  | 1<<11    | 2048 |
| IEEE1284_MODE_EPPSWE | 1<<12    | 4096 |
| IEEE1284_DEVICEID    | 1<<2     | 4 |
| IEEE1284_EXT_LINK    | 1<<14    | 16384 |

(ECPSWE/EPP/EPPSWE do NOT follow a simple sequential bit order; copy the exact
shifts from <linux/parport.h>.)

## ppdev flags (<linux/ppdev.h>)

| Name | Expression | Value |
|------|-----------|-------|
| PP_FASTWRITE | 1<<2 | 4 |
| PP_FASTREAD  | 1<<3 | 8 |
| PP_W91284PIC | 1<<4 | 16 |

## .txt.const per-arch value syntax

syzkaller's const parser (pkg/compiler/const_file.go) expects `arch:value`
pairs, NOT `value:arch`. A constant that is identical on all arches is written
as a single bare decimal; a constant that differs per arch is written as e.g.
`PPGETTIME = amd64:2148561045, 386:2148036757`. Writing it the other way round
makes syz-sysgen fail with `failed to parse int: ... parsing "amd64"`.

Worked check: PPSETMODE = _IOW('p',0x80,int) =
0x40000000 | (4<<16) | (0x70<<8) | 0x80 = 0x40047080 = 1074032768.
