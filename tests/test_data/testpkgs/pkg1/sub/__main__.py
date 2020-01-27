import debuggee
from debuggee import backchannel

debuggee.setup()
backchannel.send("ok")
