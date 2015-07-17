# Copyright (c) 2015 Francois GINDRAUD
# 
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import re
import collections
import operator
import itertools

import grako.ast

from .printer import TemplateExprPrinter

# Utils
NAME_FORMAT = re.compile ("^[A-Za-z][A-Za-z0-9_]*$")

def line_number (ast_node):
    """ Returns line number of an ast_node. """
    return ast_node.parseinfo.buffer.line_info (ast_node.parseinfo.pos).line + 1

class Error (Exception):
    pass

def alter (node, **kwargs):
    """ Copy and update AST node with provided key=value pairs. """
    new = dict (node)
    new.update (**kwargs)
    return grako.ast.AST (new)
def alter_f (node, context, **funcs):
    """
    Fast copy and update for expressions, calls f(key, context) for all given key=f
    If f returns None, returns None (recursively delete empty constructs)
    """
    new = dict (node)
    for field, func in funcs.items ():
        new[field] = func (node[field], context)
        if new[field] is None:
            return None
    return grako.ast.AST (new)
def simplify (l, keep_list = False):
    """ Removes None's elements in a list, and returns None if empty """
    cleaned = [e for e in l if e is not None]
    return cleaned if len (cleaned) > 0 or keep_list else None

# Text evaluation
class ExpandedExprTextEval:
    """
    Small class with a collection of functions to evaluate an AST expression.
    It is used to evaluate template declaration conditions.
    It is only a text evaluation ; it compares names and not their content.
    Only supports expanded expressions ; assumes templates have been expanded.
    """
    def not_allowed (self, what):
        raise Error ("{} are not allowed in text evaluation".format (what))

    def ref (self, s):
        if s.array is not None: self.not_allowed ("arrays")
        if s.var is not None: return s.var.name
    def rvalue (self, v):
        if v.ref is not None: return self.ref (v.ref)
        if v.const is not None: return v.const
    def expr (self, e):
        if e.val is not None: return self.rvalue (e.val)
        if e.op is not None: self.not_allowed ("+/- operations")
    def comp_expr (self, c):
        try: func = { "=": operator.eq, "<>": operator.ne }[c.op]
        except KeyError: self.not_allowed ("{} operations".format (c.op)) 
        return func (self.expr (c.lhs), self.expr (c.rhs))
    def bool_expr (self, e):
        if e.forall is not None: self.not_allowed ("forall constructs")
        if e.comp is not None: return self.comp_expr (e.comp)
    def and_expr (self, a):
        return all (map (self.bool_expr, a))
    def or_expr (self, o):
        return any (map (self.and_expr, o))

# Template instance generator
class TemplateInstanceGenerator:
    """
    Class to handle template instance generation and template expansion.

    An instance/context is a tuple, elements can be refered to by indexes in templates expressions.
    """
    def __init__ (self, engine, instances_data):
        self.data = instances_data
        self.engine = engine
        self.tep = TemplateExprPrinter ()
        self.text_eval = ExpandedExprTextEval ()

    # Instance constructors
    def empty (self):
        return tuple ()
    def single (self, v):
        return (v,)

    # Template expansion
    def expand (self, tpl, context):
        """ Expand a template expr in the given context """
        try:
            if tpl.arg is not None:
                try: return self.data[tpl.arg]
                except TypeError: raise Error ("wrong data format")
                except KeyError: raise Error ("name {} not found in input data".format (tpl.arg))
            def get_ref (index, field = "_key"):
                try:
                    n = int (index)
                    return context[n][field]
                except IndexError:
                    raise Error ("index {} undefined (defined = {})".format (
                        index, list (range (len (context)))))
                except KeyError:
                    raise Error ("field {} not found in context {}".format (field, context[n]))
            if tpl.key_ref is not None:
                return get_ref (tpl.key_ref)
            if tpl.field_ref is not None:
                return get_ref (tpl.field_ref.key, tpl.field_ref.field)
        except Error as e:
            raise Error ("line {}: in template {}: {}".format (
                line_number (tpl), self.tep.template (tpl), e))
            
    def name (self, name_parts, context):
        """ Expand a template name. """
        try:
            fmt = "{}".join (name_parts[0::2]) # get name_parts and insert format tokens
            expanded = [self.expand (tpl, context) for tpl in name_parts[1::2]]
            name = fmt.format (*expanded)
            if not NAME_FORMAT.match (name):
                raise Error ("malformed: {}".format (name))
            return name
        except Error as e:
            raise Error ("in name {}: {}".format (self.tep.name (name_parts), e))
    
    # Template instantiation
    def instances (self, tpl_decl, context):
        """
        Returns a generator for sub instances formed from a current instance (context) and a template declaration node.
        Each new parameter can reference all lesser indexes.
        Generated instances can be filtered with a condition (ExpandedExprTextEval)
        """
        if tpl_decl is None:
            # No template declaration at all, generate one instance with current context
            yield context
            return

        def normalize (key, value = None):
            """
            Normalize a template iterable element to a dict with:
            - element keys + _key=element_name if iterable was a dict and element was a dict
            - val=element + _key=element_name if only iterable was a dict
            - _key=element if iterable was a list
            """
            if value is None: normalized = dict ()
            elif isinstance (value, collections.Mapping): normalized = dict (value)
            else: normalized = dict (value = value)
            normalized["_key"] = key
            return normalized

        def recursive_generator (tpl_list, ctx):
            if len (tpl_list) == 0:
                # end case, return empty instance
                yield self.empty ()
                return
            # retrieve iterable
            tpl = tpl_list[0]
            iterable = self.expand (tpl, ctx)
            if isinstance (iterable, collections.Mapping):
                iterable = [normalize (k, d) for k, d in iterable.items ()]
            elif isinstance (iterable, collections.Iterable):
                iterable = [normalize (k) for k in iterable]
            else: 
                raise Error ("line {}: in template {}: expanded value is not iterable: {}".format (
                    line_number (tpl), self.tep.template (tpl), iterable))
            # generate sub_instances (make order predictable)
            iterable.sort (key = lambda e: e["_key"])
            for head_ in iterable:
                head = self.single (head_)
                for tail in recursive_generator (tpl_list[1:], ctx + head):
                    yield head + tail

        def eval_cond (context):
            if tpl_decl.cond is None:
                return True
            expanded_cond = self.engine.or_expr (tpl_decl.cond, context)
            return self.text_eval.or_expr (expanded_cond)
        
        tpl_args = [] if tpl_decl.args is None else tpl_decl.args
        for sub_instance in recursive_generator (tpl_args, context):
            instance = context + sub_instance
            if eval_cond (instance):
                yield instance
    
class TemplateEngine:
    """
    Compile the template AST to an expanded AST using the given data.

    Compilation:
    * Expands template statements and iterators
    * Convert extended syntax to conventionnal syntax
    * Checks for malformed names from the template stage
    * Removes malformed statements due to empty-set template iterators

    Defines a collection of functions to recursively expand the AST into a new one.
    Each of these functions follow the prototype <element_name> (<element_node>, <template_context>).
    """
    def __init__ (self, ast):
        self.ast = ast

    def run (self, data):
        self.ig = TemplateInstanceGenerator (self, data)
        return alter (self.ast,
                types = self.types (self.ast.types),
                decls = self.decls (self.ast.decls),
                init = self.proc_expr_construct (self.ast.init, self.ig.empty ()),
                invariants = self.proc_expr_construct_list (self.ast.invariants),
                unsafes = self.proc_expr_construct_list (self.ast.unsafes),
                transitions = self.transitions (self.ast.transitions))

    # Propagate in expressions
    def name (self, n, ctx):
        """ Name expansion is delegated to the TemplateInstanceGenerator. """
        return self.ig.name (n, ctx)
    def index_list (self, il, ctx):
        return simplify ([self.name (n, ctx) for n in il])
    def array (self, a, ctx):
        return alter_f (a, ctx, name = self.name, index = self.index_list)
    def var (self, v, ctx):
        return alter_f (v, ctx, name = self.name)
    def ref (self, s, ctx):
        if s.array is not None: return alter_f (s, ctx, array = self.array)
        if s.var is not None: return alter_f (s, ctx, var = self.var)
    def rvalue (self, v, ctx):
        if v.ref is not None: return alter_f (v, ctx, ref = self.ref)
        if v.const is not None: return v
    def expr (self, e, ctx):
        if e.val is not None: return alter_f (e, ctx, val = self.rvalue)
        if e.op is not None: return alter_f (e, ctx, lhs = self.rvalue, rhs = self.rvalue)
    def comp_expr (self, c, ctx):
        return alter_f (c, ctx, lhs = self.expr, rhs = self.expr)
    def forall_expr (self, f, ctx):
        if f.comp is not None: return alter_f (f, ctx, comp = self.comp_expr)
        if f.expr is not None: return alter_f (f, ctx, expr = self.or_expr)
    def bool_expr (self, e, ctx):
        if e.forall is not None: return alter_f (e, ctx, forall = self.forall_expr)
        if e.comp is not None: return alter_f (e, ctx, comp = self.comp_expr)

    def and_expr (self, a, ctx):
        """
        AND expression not nested in an OR expr.
        Will only be flattened in a list of expanded boolean expressions
        """
        generated = []
        for and_elem in a:
            if and_elem.expr is not None:
                generated.append (self.bool_expr (and_elem.expr, ctx))
            if and_elem.template is not None:
                for instance in self.ig.instances (and_elem.template.decl, ctx):
                    generated.extend (self.and_expr (and_elem.template.expr, instance))
            if and_elem.or_expr is not None:
                raise Error ("line {}: nested or expression not allowed here: {}".format (
                    line_number (a), TemplateExprPrinter ().and_expr (a)))
        return simplify (generated)
    def and_expr_with_nested_or (self, a, ctx):
        """
        AND expressions nested in an OR expr.
        Will be converted to a flattened expanded OR expression (list of AND expression).
        Result is an OR expression to support nested OR expressions that require duplicating the rest of the AND expression.
        """
        # templatize and classify and_elements
        bool_expr_list = []
        nested_or_exprs = []
        for and_elem in a:
            if and_elem.expr is not None:
                bool_expr_list.append (self.bool_expr (and_elem.expr, ctx))
            if and_elem.template is not None:
                for instance in self.ig.instances (and_elem.template.decl, ctx):
                    # Templates will call and_expr_with_nested_or, that returns an or_expr
                    nested_or_exprs.append (self.and_expr_with_nested_or (and_elem.template.expr, instance))
            if and_elem.or_expr is not None:
                nested_or_exprs.append (self.or_expr (and_elem.or_expr, ctx))
        bool_expr_list = simplify (bool_expr_list, keep_list = True)
        nested_or_exprs = simplify (nested_or_exprs, keep_list = True)
        # iterate on all nested_or's and_exprs combinations, combine them with the normal and_expr part
        return [sum (and_expr_combination_list, bool_expr_list)
                for and_expr_combination_list in itertools.product (*nested_or_exprs)]

    def or_expr (self, o, ctx):
        """ OR expression ; will be flattened to a list of expanded AND expressions. """
        generated = []
        for or_elem in o:
            if or_elem.expr is not None:
                generated.extend (self.and_expr_with_nested_or (or_elem.expr, ctx))
            if or_elem.template is not None:
                for instance in self.ig.instances (or_elem.template.decl, ctx):
                    generated.extend (self.and_expr_with_nested_or (or_elem.template.expr, instance))
        return simplify (generated)

    # Transitions
    def case (self, c, ctx):
        if c.cond == '_': return alter_f (c, ctx, expr = self.expr)
        else: return alter_f (c, ctx, cond = self.and_expr, expr = self.expr)
    def switch (self, s, ctx):
        """ Case list : will flatten case iterators. """
        generated = []
        for c in s:
            if c.case is not None:
                generated.append (self.case (c.case, ctx))
            if c.template is not None:
                for instance in self.ig.instances (c.template.decl, ctx):
                    generated.extend (self.switch (c.template.case_list, instance))
        return simplify (generated)
    def assign_value (self, v, ctx):
        if v.switch is not None: return alter_f (v, ctx, switch = self.switch)
        if v.expr is not None: return alter_f (v, ctx, expr = self.expr)
        if v.rand is not None: return v
    def assign (self, u, ctx):
        return alter_f (u, ctx, lhs = self.ref, rhs = self.assign_value)
    def update_list (self, l, ctx):
        """ Update list : will flatten update iterators. """
        generated = []
        for u in l:
            if u.assign is not None:
                generated.append (self.assign (u.assign, ctx))
            if u.template is not None:
                for instance in self.ig.instances (u.template.decl, ctx):
                    generated.extend (self.update_list (u.template.updates, instance))
        return simplify (generated)
    def transition (self, t, ctx):
        # allow require to be null
        # empty updates will remove transition
        return alter_f (alter (t, require = self.or_expr (t.require, ctx)),
                ctx, name = self.name, updates = self.update_list)
    def transitions (self, transitions):
        # allow no transition (cubicle error)
        generated = []
        for t in transitions:
            for instance in self.ig.instances (t.decl, self.ig.empty ()):
                generated.append (self.transition (t, instance))
        return simplify (generated, keep_list = True)
    
    # Var declarations
    def decl (self, d, ctx):
        # typename not a template
        return alter_f (d, ctx, name = self.ref)
    def decls (self, decls):
        # allow no declaration (cubicle error)
        generated = []
        for d in decls:
            for instance in self.ig.instances (d.decl, self.ig.empty ()):
                generated.append (self.decl (d, instance))
        return simplify (generated, keep_list = True)
    
    # Type declarations
    def type_enum_list (self, enum_list, ctx):
        generated = []
        for e in enum_list:
            if e.name is not None:
                generated.append (self.name (e.name, ctx))
            if e.template is not None:
                for instance in self.ig.instances (e.template.decl, ctx):
                    generated.extend (self.type_enum_list (e.template.enum, instance))
        return simplify (generated, keep_list = True) # abstract type (no enum) permitted
    def type_def (self, t, ctx):
        # typename not a template
        return alter_f (t, ctx, enum = self.type_enum_list)
    def types (self, types):
        # allow no types
        return simplify ([self.type_def (t, self.ig.empty ()) for t in types], keep_list = True)

    # Init, unsafe and invariant 
    def proc_expr_construct (self, construct, ctx):
        return alter_f (construct, ctx, expr = self.or_expr)
    def proc_expr_construct_list (self, constructs):
        generated = []
        for c in constructs:
            for instance in self.ig.instances (c.decl, self.ig.empty ()):
                generated.append (self.proc_expr_construct (c, instance))
        return simplify (generated, keep_list = True)

