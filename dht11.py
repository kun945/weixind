#!/usr/bin/env python
# encoding: utf-8

from ctypes import *

libsp = CDLL("/home/pi/source/weixind/libdht11.so")

class dth11_data(Structure):
    _fields_ = [("humidity", c_uint8),
                ("htmidity_float", c_uint8),
                ("temperature", c_uint8),
                ("temperature_float", c_uint8),
                ("checksum", c_uint8)]


class dth11_data_format(Union):
    _fields_ = [("mem", c_uint8 * 5),
                ("human", dth11_data)]


class sp_dth11(Structure):
    _fields_ = [("pin", c_int),
                ("data", dth11_data_format)
            ]

dth11_read_times = libsp.dth11_read_times
dth11_read_times.restype = c_int
dth11_read_times.argtypes = [POINTER(sp_dth11), c_int]

def read(pin):
    dt = sp_dth11()
    dt.pin = c_int(pin)
    dth11_read_times(pointer(dt), c_int(5))
    return (dt.data.human.humidity, dt.data.human.temperature)

if __name__ == '__main__':
    print read(0)
