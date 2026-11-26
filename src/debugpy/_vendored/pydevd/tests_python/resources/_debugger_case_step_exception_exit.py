def thrower(i):
    raise ValueError(i)  # raise line


def cleanup_thrower(i):
    try:
        thrower(i)  # call thrower line
    finally:
        print("finally", i)  # finally line


def via_throw(i):
    try:
        cleanup_thrower(i)  # call cleanup_thrower line
    except ValueError:  # except line
        return i * 2
    return -1


for i in range(3):
    print("call", i, "->", via_throw(i))
print("TEST SUCEEDED!")
