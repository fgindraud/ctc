Cubicle Template Compiler
=========================

Allows to generates rules, variables, unsafes and expressions by iterating on a set of data.

Why
---

Cubicle is good for checking models with arrays of arbitrary and variable size.
However it is tedious to describe fixed size structures (especially with possibly complex relations between them).
A motivating example is our cache coherence protocol, which is linked to a task graph.

Requirements 
------------

Software dependencies:

	python 3
	grako python library
	cubicle

If using Vim, _cubicle.vim_ provides syntax coloring

How to use
----------

The template language is described in _cubicle.ebnf_, as a grammar but also with comments on top.
Cubicle templates closely follows cubicle's syntax, while adding some template constructs delimited by '@' characters.
_owm.cub_ provides an example on how to use it to generate a cubicle file for our cache coherence protocol.

_generate.py_ reads a cubicle template file on its stdin, and calls the _ctc.py_ functions on its internal data structure to generate the cubicle file, which is then printed on stdout.
It provides an example of how to use the template substitution functions, and how to encode fixed sizes structures as python dict/list.

