def Call():
    b = True
    while b:        # expected
        pass        # requested
        break


if __name__ == '__main__':
    Call()
    print('TEST SUCEEDED!')