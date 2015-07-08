#!/usr/bin/env python
from template import TemplateEngine
import sys

data = {
        "T": {
            "A": {
                "dep": [],
                "access": "RW"
                },
            "B": {
                "dep": ["A"],
                "access": "RO"
                }
            }
        }

# will need cond
# will need template type enum genreation: @T@ (| Enum_@0@)
# will need template update generation: @T@ (; ...)

TemplateEngine (sys.stdin).run (sys.stdout, data)

