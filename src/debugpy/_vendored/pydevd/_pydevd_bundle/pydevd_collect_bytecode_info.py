from opcode import HAVE_ARGUMENT, EXTENDED_ARG, hasconst, opname, hasname, hasjrel, haslocal, \
    hascompare, hasfree, cmp_op
import dis
import sys
import inspect
from collections import namedtuple
from _pydevd_bundle.pydevd_constants import IS_PY38_OR_GREATER

try:
    xrange
except NameError:
    xrange = range


class TryExceptInfo(object):

    def __init__(self, try_line, is_finally=False):
        self.try_line = try_line
        self.is_finally = is_finally
        self.except_line = -1
        self.except_bytecode_offset = -1
        self.except_end_line = -1
        self.except_end_bytecode_offset = -1
        self.raise_lines_in_except = []

    def is_line_in_try_block(self, line):
        return self.try_line <= line <= self.except_line

    def is_line_in_except_block(self, line):
        return self.except_line <= line <= self.except_end_line

    def __str__(self):
        lst = [
            '{try:',
            str(self.try_line),
            ' except ',
            str(self.except_line),
            ' end block ',
            str(self.except_end_line),
        ]
        if self.raise_lines_in_except:
            lst.append(' raises: %s' % (', '.join(str(x) for x in self.raise_lines_in_except),))

        lst.append('}')
        return ''.join(lst)

    __repr__ = __str__


class ReturnInfo(object):

    def __init__(self, return_line):
        self.return_line = return_line

    def __str__(self):
        return '{return: %s}' % (self.return_line,)

    __repr__ = __str__


def _get_line(op_offset_to_line, op_offset, firstlineno, search=False):
    op_offset_original = op_offset
    while op_offset >= 0:
        ret = op_offset_to_line.get(op_offset)
        if ret is not None:
            return ret - firstlineno
        if not search:
            return ret
        else:
            op_offset -= 1
    raise AssertionError('Unable to find line for offset: %s.Info: %s' % (
        op_offset_original, op_offset_to_line))


def debug(s):
    pass


_Instruction = namedtuple('_Instruction', 'opname, opcode, starts_line, argval, is_jump_target, offset, argrepr')


def _iter_as_bytecode_as_instructions_py2(co):
    code = co.co_code
    op_offset_to_line = dict(dis.findlinestarts(co))
    labels = set(dis.findlabels(code))
    bytecode_len = len(code)
    i = 0
    extended_arg = 0
    free = None

    op_to_name = opname

    while i < bytecode_len:
        c = code[i]
        op = ord(c)
        is_jump_target = i in labels

        curr_op_name = op_to_name[op]
        initial_bytecode_offset = i

        i = i + 1
        if op < HAVE_ARGUMENT:
            yield _Instruction(curr_op_name, op, _get_line(op_offset_to_line, initial_bytecode_offset, 0), None, is_jump_target, initial_bytecode_offset, '')

        else:
            oparg = ord(code[i]) + ord(code[i + 1]) * 256 + extended_arg

            extended_arg = 0
            i = i + 2
            if op == EXTENDED_ARG:
                extended_arg = oparg * 65536

            if op in hasconst:
                yield _Instruction(curr_op_name, op, _get_line(op_offset_to_line, initial_bytecode_offset, 0), co.co_consts[oparg], is_jump_target, initial_bytecode_offset, repr(co.co_consts[oparg]))
            elif op in hasname:
                yield _Instruction(curr_op_name, op, _get_line(op_offset_to_line, initial_bytecode_offset, 0), co.co_names[oparg], is_jump_target, initial_bytecode_offset, repr(co.co_names[oparg]))
            elif op in hasjrel:
                argval = i + oparg
                yield _Instruction(curr_op_name, op, _get_line(op_offset_to_line, initial_bytecode_offset, 0), argval, is_jump_target, initial_bytecode_offset, "to " + repr(argval))
            elif op in haslocal:
                yield _Instruction(curr_op_name, op, _get_line(op_offset_to_line, initial_bytecode_offset, 0), co.co_varnames[oparg], is_jump_target, initial_bytecode_offset, repr(co.co_varnames[oparg]))
            elif op in hascompare:
                yield _Instruction(curr_op_name, op, _get_line(op_offset_to_line, initial_bytecode_offset, 0), cmp_op[oparg], is_jump_target, initial_bytecode_offset, cmp_op[oparg])
            elif op in hasfree:
                if free is None:
                    free = co.co_cellvars + co.co_freevars
                yield _Instruction(curr_op_name, op, _get_line(op_offset_to_line, initial_bytecode_offset, 0), free[oparg], is_jump_target, initial_bytecode_offset, repr(free[oparg]))
            else:
                yield _Instruction(curr_op_name, op, _get_line(op_offset_to_line, initial_bytecode_offset, 0), oparg, is_jump_target, initial_bytecode_offset, repr(oparg))


def _iter_instructions(co):
    if sys.version_info[0] < 3:
        iter_in = _iter_as_bytecode_as_instructions_py2(co)
    else:
        iter_in = dis.Bytecode(co)
    iter_in = list(iter_in)

    bytecode_to_instruction = {}
    for instruction in iter_in:
        bytecode_to_instruction[instruction.offset] = instruction

    if iter_in:
        for instruction in iter_in:
            yield instruction


def collect_return_info(co, use_func_first_line=False):
    if not hasattr(co, 'co_lnotab'):
        return []

    if use_func_first_line:
        firstlineno = co.co_firstlineno
    else:
        firstlineno = 0

    lst = []
    op_offset_to_line = dict(dis.findlinestarts(co))
    for instruction in _iter_instructions(co):
        curr_op_name = instruction.opname
        if curr_op_name == 'RETURN_VALUE':
            lst.append(ReturnInfo(_get_line(op_offset_to_line, instruction.offset, firstlineno, search=True)))

    return lst


def collect_try_except_info(co, use_func_first_line=False):
    if not hasattr(co, 'co_lnotab'):
        return []

    if use_func_first_line:
        firstlineno = co.co_firstlineno
    else:
        firstlineno = 0

    try_except_info_lst = []
    stack_in_setup = []

    op_offset_to_line = dict(dis.findlinestarts(co))

    for instruction in _iter_instructions(co):
        curr_op_name = instruction.opname

        if curr_op_name in ('SETUP_EXCEPT', 'SETUP_FINALLY'):
            # We need to collect try..finally blocks too to make sure that
            # the stack_in_setup we're using to collect info is correct.
            # Note: On Py3.8 both except and finally statements use 'SETUP_FINALLY'.
            try_except_info = TryExceptInfo(
                _get_line(op_offset_to_line, instruction.offset, firstlineno, search=True),
                is_finally=curr_op_name == 'SETUP_FINALLY'
            )
            try_except_info.except_bytecode_offset = instruction.argval
            try_except_info.except_line = _get_line(
                op_offset_to_line,
                try_except_info.except_bytecode_offset,
                firstlineno,
            )

            stack_in_setup.append(try_except_info)

        elif curr_op_name == 'POP_EXCEPT':
            # On Python 3.8 there's no SETUP_EXCEPT (both except and finally start with SETUP_FINALLY),
            # so, we differentiate by a POP_EXCEPT.
            if IS_PY38_OR_GREATER:
                stack_in_setup[-1].is_finally = False

        elif curr_op_name == 'RAISE_VARARGS':
            # We want to know about reraises and returns inside of except blocks (unfortunately
            # a raise appears to the debugger as a return, so, we may need to differentiate).
            if instruction.argval == 0:
                for info in stack_in_setup:
                    info.raise_lines_in_except.append(
                        _get_line(op_offset_to_line, instruction.offset, firstlineno, search=True))

        elif curr_op_name == 'END_FINALLY':  # The except block also ends with 'END_FINALLY'.
            stack_in_setup[-1].except_end_bytecode_offset = instruction.offset
            stack_in_setup[-1].except_end_line = _get_line(op_offset_to_line, instruction.offset, firstlineno, search=True)
            if not stack_in_setup[-1].is_finally:
                # Don't add try..finally blocks.
                try_except_info_lst.append(stack_in_setup[-1])
            del stack_in_setup[-1]

    while stack_in_setup:
        # On Py3 the END_FINALLY may not be there (so, the end of the function is also the end
        # of the stack).
        stack_in_setup[-1].except_end_bytecode_offset = instruction.offset
        stack_in_setup[-1].except_end_line = _get_line(op_offset_to_line, instruction.offset, firstlineno, search=True)
        if not stack_in_setup[-1].is_finally:
            # Don't add try..finally blocks.
            try_except_info_lst.append(stack_in_setup[-1])
        del stack_in_setup[-1]

    return try_except_info_lst


if sys.version_info[:2] >= (3, 9):

    def collect_try_except_info(co, use_func_first_line=False):
        # We no longer have 'END_FINALLY', so, we need to do things differently in Python 3.9
        if not hasattr(co, 'co_lnotab'):
            return []

        if use_func_first_line:
            firstlineno = co.co_firstlineno
        else:
            firstlineno = 0

        try_except_info_lst = []

        op_offset_to_line = dict(dis.findlinestarts(co))

        offset_to_instruction_idx = {}

        instructions = list(_iter_instructions(co))

        line_to_instructions = {}

        curr_line_index = firstlineno
        for i, instruction in enumerate(instructions):
            offset_to_instruction_idx[instruction.offset] = i

            new_line_index = op_offset_to_line.get(instruction.offset)
            if new_line_index is not None:
                if new_line_index is not None:
                    curr_line_index = new_line_index - firstlineno
            line_to_instructions.setdefault(curr_line_index, []).append(instruction)

        for i, instruction in enumerate(instructions):
            curr_op_name = instruction.opname
            if curr_op_name == 'SETUP_FINALLY':
                exception_end_instruction_index = offset_to_instruction_idx[instruction.argval]

                jump_instruction = instructions[exception_end_instruction_index - 1]
                if jump_instruction.opname not in('JUMP_FORWARD', 'JUMP_ABSOLUTE'):
                    continue

                next_3 = [instruction.opname for instruction in instructions[exception_end_instruction_index:exception_end_instruction_index + 3]]
                if next_3 == ['POP_TOP', 'POP_TOP', 'POP_TOP']:  # try..except without checking exception.

                    if jump_instruction.opname == 'JUMP_ABSOLUTE':
                        # On latest versions of Python 3 the interpreter has a go-backwards step,
                        # used to show the initial line of a for/while, etc (which is this
                        # JUMP_ABSOLUTE)... we're not really interested in it, but rather on where
                        # it points to.
                        except_end_instruction = instructions[offset_to_instruction_idx[jump_instruction.argval]]
                        idx = offset_to_instruction_idx[except_end_instruction.argval]
                        # Search for the POP_EXCEPT which should be at the end of the block.
                        for pop_except_instruction in reversed(instructions[:idx]):
                            if pop_except_instruction.opname == 'POP_EXCEPT':
                                except_end_instruction = pop_except_instruction
                                break
                        else:
                            continue  # i.e.: Continue outer loop

                    else:
                        except_end_instruction = instructions[offset_to_instruction_idx[jump_instruction.argval]]

                elif next_3 and next_3[0] == 'DUP_TOP':  # try..except AssertionError.
                    for jump_if_not_exc_instruction in instructions[exception_end_instruction_index + 1:]:
                        if jump_if_not_exc_instruction.opname == 'JUMP_IF_NOT_EXC_MATCH':
                            except_end_instruction = instructions[offset_to_instruction_idx[jump_if_not_exc_instruction.argval]]
                            break
                    else:
                        continue  # i.e.: Continue outer loop

                else:
                    # i.e.: we're not interested in try..finally statements, only try..except.
                    continue

                try_except_info = TryExceptInfo(
                    _get_line(op_offset_to_line, instruction.offset, firstlineno, search=True),
                    is_finally=False
                )
                try_except_info.except_bytecode_offset = instruction.argval
                try_except_info.except_line = _get_line(
                    op_offset_to_line,
                    try_except_info.except_bytecode_offset,
                    firstlineno,
                )

                try_except_info.except_end_bytecode_offset = except_end_instruction.offset
                try_except_info.except_end_line = _get_line(op_offset_to_line, except_end_instruction.offset, firstlineno, search=True)
                try_except_info_lst.append(try_except_info)

                for raise_instruction in instructions[i:offset_to_instruction_idx[try_except_info.except_end_bytecode_offset]]:
                    if raise_instruction.opname == 'RAISE_VARARGS':
                        if raise_instruction.argval == 0:
                            try_except_info.raise_lines_in_except.append(
                                _get_line(op_offset_to_line, raise_instruction.offset, firstlineno, search=True))

        return try_except_info_lst


class _Uncompyler(object):

    def __init__(self, co, firstlineno):
        self.co = co
        self.firstlineno = firstlineno
        self.instructions = list(_iter_instructions(co))

    def _decorate_jump_target(self, instruction, instruction_repr):
        if instruction.is_jump_target:
            return '|%s|%s' % (instruction.offset, instruction_repr)

        return instruction_repr

    def _next_instruction_to_str(self, line_to_contents):
        dec = self._decorate_jump_target

        instruction = self.instructions.pop(0)
        if instruction.opname in ('LOAD_GLOBAL', 'LOAD_FAST', 'LOAD_CONST'):
            if self.instructions:
                next_instruction = self.instructions[0]
                if next_instruction.opname == 'STORE_FAST':
                    self.instructions.pop(0)
                    return '%s = %s' % (dec(next_instruction, next_instruction.argrepr), dec(instruction, instruction.argrepr))

                if next_instruction.opname == 'CALL_FUNCTION':
                    if next_instruction.argval == 0:
                        self.instructions.pop(0)
                        return dec(instruction, '%s()' % (instruction.argrepr))

                if next_instruction.opname == 'RETURN_VALUE':
                    self.instructions.pop(0)
                    return dec(instruction, 'return %s' % (instruction.argrepr))

                if next_instruction.opname == 'RAISE_VARARGS' and next_instruction.argval == 1:
                    self.instructions.pop(0)
                    return dec(next_instruction, 'raise %s' % dec(instruction, instruction.argrepr))

        if instruction.opname == 'LOAD_CONST':
            if inspect.iscode(instruction.argval):
                code_line_to_contents = _Uncompyler(instruction.argval, self.firstlineno).build_line_to_contents()
                for contents in code_line_to_contents.values():
                    contents.insert(0, '    ')
                line_to_contents.update(code_line_to_contents)

        if instruction.opname == 'RAISE_VARARGS':
            if instruction.argval == 0:
                return 'raise'

        if instruction.opname == 'SETUP_FINALLY':
            return dec(instruction, 'try(%s):' % (instruction.argrepr,))

        if instruction.argrepr:
            return dec(instruction, '%s(%s)' % (instruction.opname, instruction.argrepr,))

        if instruction.argval:
            return dec(instruction, '%s{%s}' % (instruction.opname, instruction.argval,))

        return dec(instruction, instruction.opname)

    def build_line_to_contents(self):
        co = self.co
        firstlineno = self.firstlineno

        # print('----')
        # for instruction in self.instructions:
        #     print(instruction)
        # print('----\n\n')

        op_offset_to_line = dict(dis.findlinestarts(co))
        curr_line_index = 0

        line_to_contents = {}

        instructions = self.instructions
        while instructions:
            instruction = instructions[0]
            new_line_index = op_offset_to_line.get(instruction.offset)
            if new_line_index is not None:
                if new_line_index is not None:
                    curr_line_index = new_line_index - firstlineno

            lst = line_to_contents.setdefault(curr_line_index, [])
            lst.append(self._next_instruction_to_str(line_to_contents))
        return line_to_contents

    def uncompyle(self):
        line_to_contents = self.build_line_to_contents()
        from io import StringIO
        stream = StringIO()
        last_line = 0
        for line, contents in line_to_contents.items():
            while last_line < line - 1:
                stream.write(u'%s.\n' % (last_line + 1,))
                last_line += 1

            if contents and not contents[0].strip():
                # i.e.: don't put a comma after the indentation.
                stream.write(u'%s. %s%s\n' % (line, contents[0], ', '.join(contents[1:])))
            else:
                stream.write(u'%s. %s\n' % (line, ', '.join(contents)))
            last_line = line

        return stream.getvalue()


def uncompyle(co, use_func_first_line=False):
    '''
    A simple uncompyle of bytecode.

    It does not attempt to provide a full uncompyle to Python, rather, it provides a low-level
    representation of the bytecode, respecting the lines (so, its target is making the bytecode
    easier to grasp and not providing the original source code).

    Note that it does show jump locations/targets and converts some common bytecode constructs to
    Python code to make it a bit easier to understand.
    '''
    # Reference for bytecodes:
    # https://docs.python.org/3/library/dis.html
    if use_func_first_line:
        firstlineno = co.co_firstlineno
    else:
        firstlineno = 0

    return _Uncompyler(co, firstlineno).uncompyle()

