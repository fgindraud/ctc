#!/usr/bin/env python

import sys
import itertools
import collections

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
                matched = self._scanre ("(?:[^(*]|\((?!\*)|\*(?!\)))*(\(\*|\*\))") # match next '(*' or '*)'
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
        """ Generate a new ast with substituted templates """
        def line (node):
            return node.parseinfo.buffer.line_info (node.parseinfo.pos).line + 1
        def alter (node, **kwargs):
            """ copy and update AST node with new args """
            new = dict (node)
            new.update (**kwargs)
            return grako.ast.AST (new)
        def alter_f (node, instance, **funcs):
            """ fast copy and update for expressions, calls f(key, instance) for all given key=f """
            new = dict (node)
            for field, func in funcs.items ():
                new[field] = func (node[field], instance)
            return grako.ast.AST (new)

        # Template substitution
        def expand_template (t, instance, in_substitution = False):
            if t.arg is not None:
                if in_substitution:
                    raise TemplateError ("introducing new arg in substitution: {}".format (t.arg))
                try:
                    instances = data[t.arg]
                except TypeError:
                    raise TemplateError ("input data must be a map of list/maps")
                except KeyError:
                    raise TemplateError ("template arg not found in input data: {}".format (t.arg))
                
                # get the set of instances, normalize it to a list of dicts with _instance fields to store the instance name
                def normalize (instance_name, instance_dict = {}):
                    new = dict (instance_dict)
                    new["_instance"] = instance_name
                    return new
                if isinstance (instances, collections.Mapping):
                    return [normalize (i, d) for i, d in instances.items ()]
                elif isinstance (instances, collections.Iterable):
                    return [normalize (i) for i in instances]
                else:
                    raise TemplateError ("input data for template param {} is not a map or iterable".format (t.arg))

            def get_ref (instance_index, field_name = "_instance"):
                try:
                    n = int (instance_index)
                    return instance[n][field_name] # normalized above
                except IndexError:
                    raise TemplateError ("substitution index {} undefined (defined = [0,{}[)".format (instance_index, len (instance)))
                except KeyError:
                    raise TemplateError ("field {} not found in instance {}".format (field_name, instance[n]))
            if t.key_ref is not None:
                return get_ref (t.key_ref)
            if t.field_ref is not None:
                return get_ref (t.field_ref.key, t.field_ref.field)

        def template_instances (node, instance = []):
            try:
                template_list = [] if node.template is None else node.template
                def get_iterable (t):
                    iterable = expand_template (t, instance)
                    if not isinstance (iterable, collections.Iterable):
                        raise TemplateError ("param is not iterable: {}".format (t))
                    return iterable
                return itertools.product (*[get_iterable (t) for t in template_list])
            except TemplateError as e:
                raise TemplateError ("line {}: {}".format (line (node), e))

        def gen_name (name_elements, instance):
            fmt = "{}".join (name_elements[0::2]) # get name_parts and insert format tokens
            expanded = [expand_template (t, instance, in_substitution = True) for t in name_elements[1::2]]
            return fmt.format (*expanded)
        
        # Propagate in expressions
        def gen_index_list (l, instance):
            return [gen_name (i, instance) for i in l]
        def gen_array (a, instance):
            return alter_f (a, instance, name = gen_name, index = gen_index_list)
        def gen_var (v, instance):
            return alter_f (v, instance, name = gen_name)
        def gen_ref (s, instance):
            # Add line on error (name gets a string and has no parse_info)
            try:
                if s.array is not None: return alter_f (s, instance, array = gen_array)
                if s.var is not None: return alter_f (s, instance, var = gen_var)
            except TemplateError as e:
                raise TemplateError ("line {}: {}".format (line (s), e))
        def gen_rvalue (v, instance):
            if v.ref is not None: return alter_f (v, instance, ref = gen_ref)
            if v.const is not None: return v.const 
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
        # expand template iterators, transforming and/or expr in plain lists
        def gen_and_expr (a, instance):
            generated = []
            for and_elem in a:
                if and_elem.expr is not None:
                    generated.append (gen_bool_expr (and_elem.expr, instance))
                if and_elem.template is not None:
                    for new in template_instances (and_elem.template):
                        generated.append (gen_bool_expr (and_elem.template.expr, instance + list (new)))
            return generated
        def gen_or_expr (o, instance):
            generated = []
            for or_elem in o:
                if or_elem.expr is not None:
                    generated.append (gen_and_expr (or_elem.expr, instance))
                if or_elem.template is not None:
                    for new in template_instances (or_elem.template):
                        generated.append (gen_and_expr (or_elem.template.expr, instance + list (new)))
            return generated
        def gen_case (c, instance):
            if c.cond == '_': return alter_f (c, instance, expr = gen_expr)
            else: return alter_f (c, instance, cond = gen_and_expr, expr = gen_expr)
        def gen_switch (s, instance):
            return [gen_case (c, instance) for c in s]
        def gen_assign_value (v, instance):
            if v.switch is not None: return alter_f (v, instance, switch = gen_switch)
            if v.expr is not None: return alter_f (v, instance, expr = gen_expr)
            if v.rand is not None: return v
        def gen_update (u, instance):
            return alter_f (u, instance, lhs = gen_ref, rhs = gen_assign_value)
        def gen_trans_body (b, instance):
            return [gen_update (u, instance) for u in b]

        # Top level constructs handling
        def gen_decls (decls):
            generated = []
            for d in decls:
                for instance in template_instances (d):
                    generated.append (alter (d, name = gen_ref (d.name, instance), template = None))
            return generated 
        
        def gen_proc_expr_construct (construct, instance = []):
            return alter (construct, expr = gen_or_expr (construct.expr, instance), template = None)
        def gen_proc_expr_construct_list (constructs):
            generated = []
            for c in constructs:
                for instance in template_instances (c):
                    generated.append (gen_proc_expr_construct (c, instance))
            return generated

        def gen_transitions (transitions):
            generated = []
            for t in transitions:
                for instance in template_instances (t):
                    generated.append (alter (t,
                        name = gen_name (t.name, instance),
                        require = gen_or_expr (t.require, instance),
                        updates = gen_trans_body (t.updates, instance),
                        template = None))
            return generated

        return alter (self.ast, 
                decls = gen_decls (self.ast.decls),
                init = gen_proc_expr_construct (self.ast.init),
                invariants = gen_proc_expr_construct_list (self.ast.invariants),
                unsafes = gen_proc_expr_construct_list (self.ast.unsafes),
                transitions = gen_transitions (self.ast.transitions)
                )

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

# Test


data = {
        "T": [ "A", "B" ]
        }

engine = TemplateEngine (sys.stdin)
engine.run (sys.stdout, data)

