#!/bin/python
#author: tobias mueller 13.6.13
#byteplay test

from sys import version_info
from dis import dis
from _pydevd_frame_eval.vendored.bytecode import Bytecode, ConcreteBytecode, dump_bytecode
from pprint import pprint

def f(a, b):
#    res = a + b
    return

def g(a, b):
    res = a + b if a < b else b + a
    r = 0
    for a in range(res):
        r += 1
    return r or 2

for x in (f, g):
    #get byte code for f
    dis(x)
    print(f.__code__.co_code)
    c = Bytecode.from_code(x.__code__)
    cc = ConcreteBytecode.from_code(x.__code__)
    dump_bytecode(c)
    dump_bytecode(cc)

    #generate byte code
    cnew = c.to_code()

    x.__code__ = cnew
    dis(x)

    print(x(3,5))
