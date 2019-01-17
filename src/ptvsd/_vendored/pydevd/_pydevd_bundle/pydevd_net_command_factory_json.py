from _pydev_bundle._pydev_imports_tipper import TYPE_IMPORT, TYPE_CLASS, TYPE_FUNCTION, TYPE_ATTR, \
    TYPE_BUILTIN, TYPE_PARAM
from _pydev_bundle.pydev_is_thread_alive import is_thread_alive
from _pydev_bundle.pydev_override import overrides
from _pydevd_bundle._debug_adapter import pydevd_schema
from _pydevd_bundle.pydevd_comm_constants import CMD_THREAD_CREATE, CMD_RETURN
from _pydevd_bundle.pydevd_constants import get_thread_id
from _pydevd_bundle.pydevd_net_command import NetCommand
from _pydevd_bundle.pydevd_net_command_factory_xml import NetCommandFactory
from _pydevd_bundle.pydevd_utils import get_non_pydevd_threads


class NetCommandFactoryJson(NetCommandFactory):
    '''
    Factory for commands which will provide messages as json (they should be
    similar to the debug adapter where possible, although some differences
    are currently Ok).

    Note that it currently overrides the xml version so that messages
    can be done one at a time (any message not overridden will currently
    use the xml version) -- after having all messages handled, it should
    no longer use NetCommandFactory as the base class.
    '''

    @overrides(NetCommandFactory.make_thread_created_message)
    def make_thread_created_message(self, thread):

        # Note: the thread id for the debug adapter must be an int
        # (make the actual id from get_thread_id respect that later on).
        msg = pydevd_schema.ThreadEvent(
            pydevd_schema.ThreadEventBody('started', get_thread_id(thread)),
        )

        return NetCommand(CMD_THREAD_CREATE, 0, msg.to_dict(), is_json=True)

    @overrides(NetCommandFactory.make_list_threads_message)
    def make_list_threads_message(self, seq):
        threads = []
        for thread in get_non_pydevd_threads():
            if is_thread_alive(thread):
                thread_schema = pydevd_schema.Thread(id=get_thread_id(thread), name=thread.getName())
                threads.append(thread_schema.to_dict())

        body = pydevd_schema.ThreadsResponseBody(threads)
        response = pydevd_schema.ThreadsResponse(
            request_seq=seq, success=True, command='threads', body=body)

        return NetCommand(CMD_RETURN, 0, response.to_dict(), is_json=True)

    @overrides(NetCommandFactory.make_get_completions_message)
    def make_get_completions_message(self, seq, completions, qualifier, start):
        COMPLETION_TYPE_LOOK_UP = {
            TYPE_IMPORT: pydevd_schema.CompletionItemType.MODULE,
            TYPE_CLASS: pydevd_schema.CompletionItemType.CLASS,
            TYPE_FUNCTION: pydevd_schema.CompletionItemType.FUNCTION,
            TYPE_ATTR: pydevd_schema.CompletionItemType.FIELD,
            TYPE_BUILTIN: pydevd_schema.CompletionItemType.KEYWORD,
            TYPE_PARAM: pydevd_schema.CompletionItemType.VARIABLE,
        }

        qualifier = qualifier.lower()
        qualifier_len = len(qualifier)
        targets = []
        for completion in completions:
            label = completion[0]
            if label.lower().startswith(qualifier):
                completion = pydevd_schema.CompletionItem(
                    label=label, type=COMPLETION_TYPE_LOOK_UP[completion[3]], start=start, length=qualifier_len)
                targets.append(completion.to_dict())

        body = pydevd_schema.CompletionsResponseBody(targets)
        response = pydevd_schema.CompletionsResponse(
            request_seq=seq, success=True, command='completions', body=body)
        return NetCommand(CMD_RETURN, 0, response.to_dict(), is_json=True)

