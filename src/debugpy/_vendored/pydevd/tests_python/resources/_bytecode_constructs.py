from contextlib import contextmanager


def method1():

    _a = 0
    while _a < 2:  # break while
        _a += 1


def method2():
    try:
        raise AssertionError()
    except:  # break except
        pass


@contextmanager
def ctx():
    yield ''


def method3():
    with ctx() as a:  # break with
        return a


def method4():
    _a = 0
    for i in range(2):  # break for
        _a = i


def method5():
    try:  # break try 1
        _a = 10
    finally:
        _b = 10


def method6():
    try:
        _a = 10  # break try 2
    finally:
        _b = 10


def method7():
    try:
        _a = 10
    finally:
        _b = 10  # break finally 1


def method8():
    try:
        raise AssertionError()
    except:  # break except 2
        _b = 10
    finally:
        _c = 20


def method9():
    try:
        _a = 10
    except:
        _b = 10
    finally:_c = 20  # break finally 2


def method10():
    _a = {
        0: 0,
        1: 1,  # break in dict
        2: 2,
    }


def method11():
    a = 11
    if a == 10:
        a = 20
    else: a = 30  # break else


if __name__ == '__main__':
    method1()
    method2()
    method3()
    method4()
    method5()
    method6()
    method7()
    method8()
    method9()
    method10()
    method11()
    print('TEST SUCEEDED')
