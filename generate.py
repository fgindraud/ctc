#!/usr/bin/env python
import ctc
import sys

data = {
        "Tasks": {
            "A": {
                "dep": [],
                "accesses": {
                    0: dict(mode = "C")
                    }
                },
            "B": {
                "dep": ["A"],
                "accesses": {
                    0: dict (mode = "RW", read = "D_A")
                    }
                },
            "C": {
                "dep": ["B"],
                "accesses": {
                    0: dict (mode = "RO", read = "D_B")
                    }
                }
            },
        "Regions": range (1)
        }

try: ctc.CubicleTemplateCompiler (sys.stdin).run (sys.stdout, data)
except ctc.Error as e: print ("ctc: {}".format (e), file=sys.stderr)

