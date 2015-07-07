#!/usr/bin/env python
from template import TemplateEngine
import sys

data = {
        "T": [ "A", "B" ],
        "R": []
        }

TemplateEngine (sys.stdin).run (sys.stdout, data)

