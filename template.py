#!/usr/bin/env python

import sys
import itertools
import collections
import re

try:
    import grako.buffering
    import grako.exceptions
    import grako.ast
except ImportError:
    sys.stderr.write ("grako python module not found, please install it\n")
    raise

# Generate the parser if not found
try:
    import cubicle_parser
except ImportError:
    import os
    os.system ("python -m grako -m Cubicle -o cubicle_parser.py cubicle.ebnf")
    import cubicle_parser

class TemplateError (Exception):
    pass

class CubicleCommentBuffer (grako.buffering.Buffer):
    """ Handles removing the caml-style recursive comments in cubicle """
    def eat_comments (self):
        if self.match ("(*"):
            level = 1
            while level > 0:
                matched = self._scanre ("(?:.|\n)*?(\(\*|\*\))") # match next '(*' or '*)'
                if not matched:
                    raise grako.exceptions.ParseError ("Unmatched comment at line {}".format (self.line_info ().line + 1))
                if matched.group (1) == "(*":
                    level += 1
                if matched.group (1) == "*)":
                    level -= 1
                self.move (len (matched.group (0)))

class TemplateEngine:
    """ Main template class. init with template, and run with data and output stream """ 
    def __init__ (self, cin):
        parser = cubicle_parser.CubicleParser (parseinfo = True)
        buf = CubicleCommentBuffer (cin.read ())
        self.ast = parser.parse (buf, "model")

    def run (self, cout, data):
        self.output_ast (cout, self.substitute (data))

    def substitute (self, data):
        """
        Generate a new ast with substituted templates

        Checks for malformed names
        Removes malformed statements due to empty-set iterations
        """
        NAME_FORMAT = re.compile ("^[A-Za-z][A-Za-z0-9_]*$")

        def line (node):
            return node.parseinfo.buffer.line_info (node.parseinfo.pos).line + 1
        def template_str (t):
            if t.arg is not None: return t.arg
            if t.key_ref is not None: return t.key_ref
            if t.field_ref is not None: return "{}.{}".format (t.field_ref.key, t.field_ref.field)
        def template_name_str (t_name):
            name_parts = t_name[:]
            name_parts[1::2] = map (template_str, name_parts[1::2]) # pretty print templates
            return "@".join (name_parts) 

        def alter (node, **kwargs):
            """ copy and update AST node with new args """
            new = dict (node)
            new.update (**kwargs)
            return grako.ast.AST (new)
        def alter_f (node, instance, **funcs):
            """
            Fast copy and update for expressions, calls f(key, instance) for all given key=f
            If f returns None, returns None (recursively delete empty constructs)
            """
            new = dict (node)
            for field, func in funcs.items ():
                new[field] = func (node[field], instance)
                if new[field] is None:
                    return None
            return grako.ast.AST (new)
        def simplify (l, keep_list = False):
            """ Removes None's elements in a list, and returns None if empty """
            cleaned = [e for e in l if e is not None]
            return cleaned if len (cleaned) > 0 or keep_list else None

        # Template substitution
        def expand_template (t, instance):
            try:
                if t.arg is not None:
                    try: return data[t.arg]
                    except TypeError: raise TemplateError ("wrong data format")
                    except KeyError: raise TemplateError ("arg {} not found in input data".format (t.arg))
                def get_ref (index, field = "_key"):
                    try:
                        n = int (index)
                        return instance[n][field]
                    except IndexError:
                        raise TemplateError ("instance index {} undefined (defined = [0,{}[)" .format (index, len (instance)))
                    except KeyError:
                        raise TemplateError ("field {} not found in instance {}".format (field_name, instance[n]))
                if t.key_ref is not None:
                    return get_ref (t.key_ref)
                if t.field_ref is not None:
                    return get_ref (t.field_ref.key, t.field_ref.field)
            except TemplateError as e:
                raise TemplateError ("line {}: {}".format (line (t), e))
                
        def template_instances (node, instance = tuple ()):
            template_list = [] if node.template is None else node.template
            def get_iterable (t):
                try:
                    iterable = expand_template (t, instance)
                    # normalize it to a dict with _key storing the element key or simple value
                    def normalize (key, dict_ = {}):
                        normalized = dict (dict_)
                        normalized["_key"] = key
                        return normalized
                    if isinstance (iterable, collections.Mapping):
                        return [normalize (k, d) for k, d in iterable.items ()]
                    elif isinstance (iterable, collections.Iterable):
                        return [normalize (k) for k in iterable]
                    else: 
                        raise TemplateError ("template value is not iterable: {}".format (iterable))
                except TemplateError as e:
                    raise TemplateError ("in declaration @{}@: {}".format (template_str (t), e))
            return itertools.product (*[get_iterable (t) for t in template_list])
        
        def gen_name (name_elements, instance):
            try:
                fmt = "{}".join (name_elements[0::2]) # get name_parts and insert format tokens
                expanded = [expand_template (t, instance) for t in name_elements[1::2]]
                name = fmt.format (*expanded)
                if not NAME_FORMAT.match (name):
                    raise TemplateError ("malformed: {}".format (name))
                return name
            except TemplateError as e:
                raise TemplateError ("in name {}: {}".format (template_name_str (name_elements), e))
        
        # Propagate in expressions
        def gen_index_list (l, instance):
            return simplify ([gen_name (i, instance) for i in l])
        def gen_array (a, instance):
            return alter_f (a, instance, name = gen_name, index = gen_index_list)
        def gen_var (v, instance):
            return alter_f (v, instance, name = gen_name)
        def gen_ref (s, instance):
            if s.array is not None: return alter_f (s, instance, array = gen_array)
            if s.var is not None: return alter_f (s, instance, var = gen_var)
        def gen_rvalue (v, instance):
            if v.ref is not None: return alter_f (v, instance, ref = gen_ref)
            if v.const is not None: return v
        def gen_expr (e, instance):
            if e.val is not None: return alter_f (e, instance, val = gen_rvalue)
            if e.op is not None: return alter_f (e, instance, lhs = gen_rvalue, rhs = gen_rvalue)
        def gen_comp_expr (c, instance):
            return alter_f (c, instance, lhs = gen_expr, rhs = gen_expr)
        def gen_forall_expr (f, instance):
            if f.comp is not None: return alter_f (f, instance, comp = gen_comp_expr)
            if f.expr is not None: return alter_f (f, instance, expr = gen_or_expr)
        def gen_bool_expr (e, instance):
            if e.forall is not None: return alter_f (e, instance, forall = gen_forall_expr)
            if e.comp is not None: return alter_f (e, instance, comp = gen_comp_expr)
        def gen_and_expr (a, instance):
            # expand and template iterators
            generated = []
            for and_elem in a:
                if and_elem.expr is not None:
                    generated.append (gen_bool_expr (and_elem.expr, instance))
                if and_elem.template is not None:
                    for new in template_instances (and_elem.template, instance):
                        generated.extend (gen_and_expr (and_elem.template.expr, instance + new))
            return simplify (generated)
        def gen_or_expr (o, instance):
            # expand or template iterators
            generated = []
            for or_elem in o:
                if or_elem.expr is not None:
                    generated.append (gen_and_expr (or_elem.expr, instance))
                if or_elem.template is not None:
                    for new in template_instances (or_elem.template, instance):
                        generated.append (gen_and_expr (or_elem.template.expr, instance + new))
            return simplify (generated)
        def gen_case (c, instance):
            if c.cond == '_': return alter_f (c, instance, expr = gen_expr)
            else: return alter_f (c, instance, cond = gen_and_expr, expr = gen_expr)
        def gen_switch (s, instance):
            return simplify ([gen_case (c, instance) for c in s])
        def gen_assign_value (v, instance):
            if v.switch is not None: return alter_f (v, instance, switch = gen_switch)
            if v.expr is not None: return alter_f (v, instance, expr = gen_expr)
            if v.rand is not None: return v
        def gen_update (u, instance):
            return alter_f (u, instance, lhs = gen_ref, rhs = gen_assign_value)
        def gen_trans_body (b, instance):
            return simplify ([gen_update (u, instance) for u in b])
        def gen_transition (t, instance):
            # allow require to be null
            # empty updates will remove transition
            return alter_f (alter (t, require = gen_or_expr (t.require, instance)),
                    instance, name = gen_name, updates = gen_trans_body)
        def gen_decl (d, instance):
            # typename not a template yet
            return alter_f (d, instance, name = gen_ref) 

        # Top level constructs handling
        def gen_decls (decls):
            generated = []
            for d in decls:
                for instance in template_instances (d):
                    generated.append (gen_decl (d, instance))
            return simplify (generated)
        
        def gen_proc_expr_construct (construct, instance = tuple ()):
            return alter_f (construct, instance, expr = gen_or_expr)
        def gen_proc_expr_construct_list (constructs, keep_list = False):
            generated = []
            for c in constructs:
                for instance in template_instances (c):
                    generated.append (gen_proc_expr_construct (c, instance))
            return simplify (generated, keep_list = keep_list)

        def gen_transitions (transitions):
            generated = []
            for t in transitions:
                for instance in template_instances (t):
                    generated.append (gen_transition (t, instance))
            return simplify (generated)

        new_ast = alter (self.ast, 
                decls = gen_decls (self.ast.decls),
                init = gen_proc_expr_construct (self.ast.init),
                invariants = gen_proc_expr_construct_list (self.ast.invariants, keep_list = True),
                unsafes = gen_proc_expr_construct_list (self.ast.unsafes),
                transitions = gen_transitions (self.ast.transitions))

        if new_ast.decls is None:
            raise TemplateError ("no variable declaration in output")
        if new_ast.init is None:
            raise TemplateError ("init body is empty")
        if new_ast.unsafes is None:
            raise TemplateError ("no unsafe statement")
        if new_ast.transitions is None:
            raise TemplateError ("no transition statement")
        return new_ast

    def output_ast (self, stream, ast):
        """ Generate cubicle code for template-substituted ast """
        def write (fmt, *args):
            stream.write (fmt.format (*args) + "\n")

        def ref (s):
            if s.array is not None: return s.array.name + "[" + ", ".join (s.array.index) + "]"
            if s.var is not None: return s.var.name
        def rvalue (v):
            if v.ref is not None: return ref (v.ref)
            if v.const is not None: return v.const
        def expr (e):
            if e.val is not None: return rvalue (e.val)
            if e.op is not None: return "{} {} {}".format (rvalue (e.lhs), e.op, rvalue (e.rhs))
        def comp_expr (c):
            return "{} {} {}".format (expr (c.lhs), c.op, expr (c.rhs))
        def forall_expr (f):
            if f.comp is not None: return "forall_other {}. {}".format (f.name, comp_expr (f.comp))
            if f.expr is not None: return "forall_other {}. ({})".format (f.name, or_expr (f.expr))
        def bool_expr (e):
            if e.forall is not None: return forall_expr (e.forall)
            if e.comp is not None: return comp_expr (e.comp)
        # here and/or expr are plain lists
        def and_expr (a):
            return " && ".join (bool_expr (e) for e in a)
        def or_expr (o):
            return " || ".join (and_expr (a) for a in o)

        def write_proc_expr_construct (s, name):
            write ("{} ({}) {{ {} }}", name, " ".join (s.procs), or_expr (s.expr))

        if ast.size_proc is not None:
            write ("number_procs {}", ast.size_proc)
        for t in ast.types:
            if t.enum is not None:
                write ("type {} = {}", t.name, " | ".join (t.enum));
            else:
                write ("type {}", t.name)
        for d in ast.decls:
            write ("{} {} : {}", d.kind, ref (d.name), d.typename)
        write_proc_expr_construct (ast.init, "init")
        for i in ast.invariants:
            write_proc_expr_construct (i, "invariant")
        for u in ast.unsafes:
            write_proc_expr_construct (u, "unsafe")
        for t in ast.transitions:
            write ("transition {} ({})", t.name, " ".join (t.procs))
            if t.require is not None:
                write ("\trequires {{ {} }}", or_expr (t.require))
            write ("{{")
            for u in t.updates:
                if u.rhs.switch is not None:
                    write ("\t{} := case", ref (u.lhs))
                    for c in u.rhs.switch:
                        if c.cond == "_":
                            write ("\t\t| _ : {}", expr (c.expr))
                        else:
                            write ("\t\t| {} : {}", and_expr (c.cond), expr (c.expr))
                    write ("\t;")
                if u.rhs.expr is not None:
                    write ("\t{} := {};", ref (u.lhs), expr (u.rhs.expr))
                if u.rhs.rand is not None:
                    write ("\t{} := ?;", ref (u.lhs))
            write ("}}")

