def full_function():
    # Note that this function is not called, it's there just to make the mapping explicit.
    a = 1  # map to cell1, line 2
    b = 2  # map to cell1, line 3

    c = 3  # map to cell2, line 2
    d = 4  # map to cell2, line 3


def create_code():
    cell1_code = compile(''' # line 1
a = 1  # line 2
b = 2  # line 3
''', '<cell1>', 'exec')

    cell2_code = compile('''# line 1
c = 3  # line 2
d = 4  # line 3
''', '<cell2>', 'exec')

    return {'cell1': cell1_code, 'cell2': cell2_code}


if __name__ == '__main__':
    code = create_code()
    exec(code['cell1'])
    exec(code['cell1'])

    exec(code['cell2'])
    exec(code['cell2'])
    print('TEST SUCEEDED')
