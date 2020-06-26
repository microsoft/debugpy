# -*- coding: utf-8 -*-
import sys
import debuggee


def ಏನಾದರೂ_ಮಾಡು():
    print("ಏನೋ ಮಾಡಿದೆ".encode(sys.stdout.encoding, errors="replace"))  # @bp


debuggee.setup()
ಏನಾದರೂ_ಮಾಡು()
