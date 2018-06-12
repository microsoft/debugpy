def method3():
    raise IndexError('foo')

def method2():
    return method3()
    
def method1():
    try:
        method2()
    except:
        pass  # Ok, handled
        
if __name__ == '__main__':
    method1()
    print('TEST SUCEEDED!')