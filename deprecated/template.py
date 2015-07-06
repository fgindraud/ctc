#!/usr/bin/env python

import sys
import itertools

# comments will be removed entirely and can be recursive
#
# Will replicate the var def line for all Ts (so must be one per line)
# ^var name_@T@...$
# ^array name_@T@[...$
#
# Will replicate transition for all Ts
# ^transition name_@T@...$
# In transition text @n@ with n an integer will be substituted with n-th transition template param, starting at 0
# 
# In unsafe and init and transition cubes:
# @T@ will replicate the line it is included in

class CubicleStream:
    def __init__ (self, stream):
        self.stream = stream
        self.buf = ""

    def find (self, pattern, start = 0):
        """ Wrapper around str.find on buffer, that returns len (buf) if not found """
        p = self.buf.find (pattern, max (start, 0))
        if p == -1:
            p = len (self.buf)
        return p

    def refill (self):
        """ Refill buffer from internal stream, returns True on success """
        r = self.stream.readline ()
        self.buf += r
        return len (r) > 0 # True if we got something from stream

    def refill_until (self, pattern, start_pos = 0):
        """
        Refill buf with internal stream until a pattern is reached (from the given starting position)
        Returns length of str until pattern (included), equivalent to pattern_pos_index + 1
        """
        while True:
            pattern_pos = self.find (pattern, start_pos)
            if pattern_pos < len (self.buf):
                return pattern_pos + 1

            # pattern not found, refilling
            if not self.refill ():
                if pattern == "\n":
                    return len (self.buf) # special case, allow readline to get last line even if no \n
                else:
                    return 0 # nothing more to get
            
            # remove comments that we just got from refill
            search_pos = self.find ("(*")
            while search_pos < len (self.buf):
                top_level_comment_started_at = search_pos
                nesting_level = 1
                search_pos += len ("(*")
                while nesting_level > 0:
                    deeper_comment_start = self.find ("(*", search_pos)
                    current_comment_end = self.find ("*)", search_pos)
                    if deeper_comment_start < current_comment_end: # hit nested comment opening first
                        nesting_level += 1
                        search_pos = deeper_comment_start + len ("(*")
                    elif current_comment_end < deeper_comment_start: # hit comment closing first
                        nesting_level -= 1
                        search_pos = current_comment_end + len ("*)")
                    else: # nothing found
                        if not self.refill (): # if no more data, kill buf until the end
                            nesting_level = 0
                            search_pos = len (self.buf)
                # cut comment nest
                self.buf = self.buf[0:top_level_comment_started_at] + self.buf[search_pos:]
                search_pos = self.find ("(*", top_level_comment_started_at) # check for next

    def read_line (self):
        """ return the next line without extracting it from the buffer """
        pos = self.refill_until ("\n")
        return self.buf[0:pos]

    def extract_line (self):
        """ returns next line, extracting it from the buffer """
        pos = self.refill_until ("\n")
        line = self.buf[0:pos]
        self.buf = self.buf[pos:]
        return line

    def extract_transition (self):
        """ returns the transition starting at current buffer start """
        end = self.refill_until ("}") # find requires{} end
        end = self.refill_until ("}", end + 1) # find transition body end
        end = self.refill_until ("\n", end) # get the complete last line
        transition = self.buf[0:end]
        self.buf = self.buf[end:]
        return transition

class TemplateEngine:
    def __init__ (self, cin, cout):
        self.cin = CubicleStream (cin)
        self.cout = cout
        self.substitutions = {
                "T": [ "A", "B" ],
                }

    def name_param_iter (self, name):
        splitted = name.split ("@") # sequence of <name-part> <template-name> <name-part> ...
        name_fmt = "{}".join (splitted[0::2]) # place str.format placeholders between name-parts
        param_instances_list = [self.substitutions[p] for p in splitted[1::2]] # list of iterables for each template param
        for instance in itertools.product (*param_instances_list): # all combinations of iterables
            yield name_fmt.format (*instance)
        
    def run (self):
        in_transition = False
        transition_lines = []

        in_comment = False

        line = self.cin.read_line ()
        while len (line) > 0:
            split_line = line.split ()

            if len (split_line) >= 2 and split_line[0] in ["var", "array"]:
                # Variable declaration, duplicate if needed
                for name in self.name_param_iter (split_line[1]):
                    split_line[1] = name
                    self.cout.write (" ".join (split_line) + "\n")
                self.cin.extract_line () # remove line
            elif len (split_line) >= 2 and split_line[0] == "transition" and False:
                # Transition opening : get the complete transition body
                transition = self.cin.extract_transition ().splitlines (True)

                # gather transition code, then generate versions. change name_param_iter to get
                # instance objects and support stuff like @0.deps@
            # handle init and unsafe. detect in_init/in_unsafe or detect @ in line ?
            else:
                self.cout.write (self.cin.extract_line ())
            line = self.cin.read_line ()

a = TemplateEngine (sys.stdin, sys.stdout)
a.run ()

