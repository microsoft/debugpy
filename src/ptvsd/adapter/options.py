# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

"""Global adapter options that are set via command line, environment variables,
or configuartion files.
"""


log_stderr = False
"""Whether detailed logs are written to stderr."""

# ide_access_token = None
# """Access token used to authenticate with the IDE."""

server_access_token = None
"""Access token used to authenticate with the server."""

adapter_access_token = None
"""Access token used by the server to authenticate with this adapter."""
