import ptvsd


def main():
    print('one')
    ptvsd.break_into_debugger()
    print('two')


main()
