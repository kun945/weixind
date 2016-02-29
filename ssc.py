#!/usr/bin/env python
# encoding: utf-8


import os
from shutil import copy
from filecmp import cmp as fcmp
from commands import getstatusoutput

_CONIFG_PATH = '/etc/shadowsocks/'
_CONIFG_NAME = sorted(os.listdir(_CONIFG_PATH))
_SHELL_PATH = '/home/pi/temp/shadowsocks/all.sh'
_SSC_LOCK = '/tmp/ssc.lock'

def ssp():
    bufs = []
    for i in range(0, len(_CONIFG_NAME)):
        bufs.append('[%d] %s' %(i, _CONIFG_NAME[i]))
    return '\n'.join(bufs)


def ssc(i, p='restart'):
    index = int(i)
    if os.path.exists(_SSC_LOCK):
        return 'is changing'

    if not index in range(0, len(_CONIFG_NAME)):
        return '%d beyond the scope of the file list.' %(index)

    o = os.path.join(_CONIFG_PATH, _CONIFG_NAME[index])
    n = os.path.join(_CONIFG_PATH, 'default.json')
    if fcmp(o, n): return '%s like %s' %(o, n)

    fd = open(_SSC_LOCK, 'w'); fd.close()

    copy(o, n)
    status, output = getstatusoutput('%s %s' %(_SHELL_PATH, p))

    os.remove(_SSC_LOCK)
    return output

def ssu():
    d = os.path.join(_CONIFG_PATH, 'default.json')
    for f in _CONIFG_NAME:
        if f == 'default.json':
            continue
        n = os.path.join(_CONIFG_PATH, f)
        if fcmp(d, n):
            fd = open(n, 'r')
            s = 'using %s\n%s' %(f, fd.read())
            fd.close()
            return s.translate(None, '\'\"<>&')
    return 'not in the folder'


def ssd():
    if os.path.exists(_SSC_LOCK):
        os.remove(_SSC_LOCK)


def sscmd(cmd):
    status, output = getstatusoutput(cmd)
    return output


def ssi():
    return sscmd('iptables -L -t nat')


def ssr():
    return sscmd('reboot')


if __name__ == '__main__':
    print ssu()
    print ssp()
    s = raw_input('Enter index: ')
    print ssc(*(int(s), 'restart'))
    exit(0)
